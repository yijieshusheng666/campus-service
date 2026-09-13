/**
 * WAV 录音器：Web Audio 采集 PCM，手动封装 WAV 头。
 *
 * 为什么不用 MediaRecorder：
 *   它默认输出 webm/opus，而智谱 ASR 只保证支持 wav/mp3。与其在后端引入
 *   ffmpeg 转码，不如在采集侧就拿出对方明确支持的格式 —— 零后端依赖。
 *
 * 切片：
 *   上游单段音频限 30 秒，所以每满 sliceSeconds 秒产出一片（onSlice 回调），
 *   录音不中断、由调用方逐片提交转写；停止时再产出最后一片（可能不足 30 秒）。
 *
 * 静音自动结束：
 *   实时算 RMS 音量，低于阈值持续 silenceMs 毫秒即触发 onAutoStop。
 *   这是「说完自动停」体验的基础，阈值给的是经验值，可按环境调。
 */

// 上游单段上限 30 秒，这里留 0.5 秒余量
const SLICE_SECONDS = 29
// 目标采样率。浏览器支持 AudioContext({sampleRate}) 时直接用 16kHz，
// 不支持时用设备实际采样率并如实写进 WAV 头 —— 上游对采样率不敏感，
// 这样就省掉了一次重采样
const TARGET_SAMPLE_RATE = 16000

export function isRecordingSupported() {
  return !!(
    typeof navigator !== 'undefined' &&
    navigator.mediaDevices?.getUserMedia &&
    (window.AudioContext || window.webkitAudioContext)
  )
}

/**
 * 把若干段 Float32 PCM 封成 16bit 单声道 WAV。
 * 导出是为了可被脚本/测试直接调用验证（字节序与头字段最容易写错）。
 * @param {Float32Array[]} chunks
 * @param {number} sampleRate
 * @returns {Blob}
 */
export function buildWav(chunks, sampleRate) {
  const total = chunks.reduce((n, c) => n + c.length, 0)
  const buffer = new ArrayBuffer(44 + total * 2)
  const view = new DataView(buffer)

  const writeStr = (offset, str) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i))
  }

  writeStr(0, 'RIFF')
  view.setUint32(4, 36 + total * 2, true) // RIFF chunk 长度
  writeStr(8, 'WAVE')
  writeStr(12, 'fmt ')
  view.setUint32(16, 16, true) // fmt 子块长度
  view.setUint16(20, 1, true) // 编码方式：1 = PCM
  view.setUint16(22, 1, true) // 声道数：1
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true) // 字节率 = 采样率 × 声道 × 位深/8
  view.setUint16(32, 2, true) // 块对齐
  view.setUint16(34, 16, true) // 位深
  writeStr(36, 'data')
  view.setUint32(40, total * 2, true)

  let offset = 44
  for (const chunk of chunks) {
    for (let i = 0; i < chunk.length; i++) {
      // 钳制到 [-1, 1]，负半轴用 0x8000 保证对称
      const s = Math.max(-1, Math.min(1, chunk[i]))
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
      offset += 2
    }
  }
  return new Blob([view], { type: 'audio/wav' })
}

/**
 * @param {object} options
 * @param {number} [options.sliceSeconds] 每片时长
 * @param {number} [options.silenceMs] 静音多久自动结束本段；0 = 关闭
 * @param {number} [options.silenceThreshold] RMS 静音门限（经验值）
 * @param {(blob: Blob, isLast: boolean) => void} [options.onSlice]
 * @param {(rms: number) => void} [options.onLevel] 实时音量（画音量条）
 * @param {() => void} [options.onAutoStop]
 * @param {(err: Error) => void} [options.onError]
 */
export function createRecorder(options = {}) {
  const {
    sliceSeconds = SLICE_SECONDS,
    silenceMs = 2000,
    silenceThreshold = 0.012,
    onSlice = () => {},
    onLevel = () => {},
    onAutoStop = () => {},
    onError = () => {}
  } = options

  let ctx = null
  let stream = null
  let source = null
  let processor = null
  let mute = null
  let chunks = []
  let samplesInSlice = 0
  let silentAccum = 0
  let recording = false

  function resetSlice() {
    chunks = []
    samplesInSlice = 0
  }

  function emitSlice(isLast) {
    if (!samplesInSlice) {
      resetSlice()
      return
    }
    // 编码 29 秒 PCM 要循环上百万次，留在 onaudioprocess 里会造成卡顿掉帧；
    // 先把数据摘出来（连同采样率），回调立即返回，编码交给下一个事件循环。
    const taken = chunks
    const rate = ctx.sampleRate
    resetSlice()
    setTimeout(() => onSlice(buildWav(taken, rate), isLast), 0)
  }

  function cleanup() {
    try { processor?.disconnect() } catch { /* 已断开 */ }
    try { source?.disconnect() } catch { /* 已断开 */ }
    try { mute?.disconnect() } catch { /* 已断开 */ }
    stream?.getTracks?.().forEach((t) => t.stop())
    try { ctx?.close() } catch { /* 已关闭 */ }
    ctx = stream = source = processor = mute = null
  }

  async function start() {
    if (recording) return true
    if (!isRecordingSupported()) {
      onError(new Error('当前浏览器不支持录音，请用 Chrome / Edge'))
      return false
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }
      })
    } catch (e) {
      onError(new Error(`无法访问麦克风：${e?.message || e}（请检查浏览器权限）`))
      return false
    }

    const AC = window.AudioContext || window.webkitAudioContext
    // 尽量直接以 16kHz 采集；部分浏览器会忽略该参数，那就照实际采样率写头
    try {
      ctx = new AC({ sampleRate: TARGET_SAMPLE_RATE })
    } catch {
      ctx = new AC()
    }
    source = ctx.createMediaStreamSource(stream)
    // 4096 帧 ≈ 16kHz 下 256ms，足够做音量与静音判断，也不会太频繁触发
    processor = ctx.createScriptProcessor(4096, 1, 1)

    processor.onaudioprocess = (e) => {
      if (!recording) return
      const input = e.inputBuffer.getChannelData(0)
      const copy = new Float32Array(input.length)
      copy.set(input)
      chunks.push(copy)
      samplesInSlice += copy.length

      let sum = 0
      for (let i = 0; i < copy.length; i++) sum += copy[i] * copy[i]
      const rms = Math.sqrt(sum / copy.length)
      onLevel(rms)

      if (silenceMs > 0) {
        const frameMs = (copy.length / ctx.sampleRate) * 1000
        if (rms < silenceThreshold) {
          silentAccum += frameMs
          if (silentAccum >= silenceMs) {
            silentAccum = 0
            onAutoStop()
            return
          }
        } else {
          silentAccum = 0
        }
      }

      if (samplesInSlice >= sliceSeconds * ctx.sampleRate) emitSlice(false)
    }

    source.connect(processor)
    // ScriptProcessorNode 必须连到输出才会触发 onaudioprocess，但直接连 destination
    // 会把麦克风输入原样播出去（啸叫）。中间串一个 0 增益节点，既触发回调又静音。
    mute = ctx.createGain()
    mute.gain.value = 0
    processor.connect(mute)
    mute.connect(ctx.destination)

    resetSlice()
    silentAccum = 0
    recording = true
    return true
  }

  /** 停止录音并产出最后一片（不足一片时长也会产出）。 */
  function stop() {
    if (!recording) return
    recording = false
    emitSlice(true)
    cleanup()
  }

  /** 放弃当前录音（不产出任何音频，用于取消）。 */
  function cancel() {
    if (!recording) return
    recording = false
    resetSlice()
    cleanup()
  }

  return {
    start,
    stop,
    cancel,
    isRecording: () => recording,
    getSampleRate: () => ctx?.sampleRate || TARGET_SAMPLE_RATE
  }
}
