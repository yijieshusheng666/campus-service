/**
 * 分句朗读器：把 SSE 逐字流按标点切成句子后逐句朗读。
 *
 * 为什么必须缓冲：
 *   面试官的问题是 SSE 逐字（delta）到达的。若每来一个字就调 speak()，
 *   听到的会是一个字一个字的机械音。这里按标点切句入队，一句念完再念下一句；
 *   `flush()` 用于流结束时把不满一句的尾巴读完。
 *
 * 用浏览器原生 speechSynthesis：
 *   零成本、零延迟、可瞬间打断（cancel），且音频不出本机。
 *   音色偏机械，但对「模拟面试官」反而合适 —— 不会让用户误以为是真人。
 */

// 句子结束符（中英文 + 换行）。
// 英文句号单独用 lookahead 处理：只在「后面是空白或结尾」时才算句末，
// 这样既能让 "ok. " 断句，又不会把 "96.4%""提升 30%" 这类小数切成两半。
const SENTENCE_END = /[。！？；!?;…\n]|\.(?=\s|$)/
// 长句里的软停顿（逗号等）：一句太长会让用户等太久才听到声音
const SOFT_BREAK = /[，,、：:]/
// 单句上限：超过则在软停顿处切开
const MAX_SENTENCE = 60

export function isSpeechSupported() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

// 朗读开关持久化：创建面试在列表页发生（首题在那儿生成、随后跳转），
// 偏好放 localStorage 才能让两个页面读到同一个值。
const PREF_KEY = 'interview:autoSpeak'

export function loadSpeakPref() {
  try {
    return localStorage.getItem(PREF_KEY) === '1'
  } catch {
    return false
  }
}

export function saveSpeakPref(enabled) {
  try {
    localStorage.setItem(PREF_KEY, enabled ? '1' : '0')
  } catch { /* 隐私模式下不可写，忽略 */ }
}

/** 列出可用语音（调试/设置用）。voices 是异步加载的，可能首次为空。 */
export function listVoices() {
  if (!isSpeechSupported()) return []
  return (window.speechSynthesis.getVoices() || []).map((v) => ({
    name: v.name,
    lang: v.lang,
    local: v.localService
  }))
}

/** 在 MAX_SENTENCE 范围内找最后一个软停顿位置；找不到返回 -1。 */
function lastSoftBreak(text) {
  for (let i = Math.min(text.length, MAX_SENTENCE); i > MAX_SENTENCE / 2; i--) {
    if (SOFT_BREAK.test(text[i - 1])) return i
  }
  return -1
}

/**
 * 从文本中切出可朗读的完整句子。
 * 导出是为了可被脚本直接验证（分句错误会导致朗读结巴或漏读）。
 * @returns {[string[], string]} [完整句子数组, 剩余不完整片段]
 */
export function splitSentences(text) {
  const sentences = []
  let rest = text
  let match

  while ((match = SENTENCE_END.exec(rest))) {
    const cut = match.index + 1
    let head = rest.slice(0, cut)
    rest = rest.slice(cut)
    // 超长句要在「整句入队之前」按软停顿拆开：否则长句子会被当成一句读完，
    // 用户要等十几秒才听到声音（早期版本把这段兜底放在后面，等于没生效）
    while (head.length > MAX_SENTENCE) {
      const soft = lastSoftBreak(head)
      if (soft <= 0) break
      sentences.push(head.slice(0, soft))
      head = head.slice(soft)
    }
    if (head.trim()) sentences.push(head)
  }

  // 残留部分：流还没结束但已经攒得很长（一直等不到结束符），同样先切出来读
  while (rest.length > MAX_SENTENCE) {
    const soft = lastSoftBreak(rest)
    if (soft <= 0) break
    sentences.push(rest.slice(0, soft))
    rest = rest.slice(soft)
  }

  return [sentences, rest]
}

/**
 * @param {object} options
 * @param {number} [options.rate] 语速
 * @param {number} [options.pitch] 音调
 * @param {number} [options.volume] 音量
 * @param {(speaking: boolean) => void} [options.onStateChange] 开始/结束朗读时回调
 */
export function createSpeaker(options = {}) {
  const { rate = 1.05, pitch = 1, volume = 1, onStateChange = () => {} } = options

  let enabled = true
  let queue = []
  let buffer = ''
  let speaking = false
  let voice = null
  let voicesBound = false

  function pickVoice() {
    const voices = window.speechSynthesis.getVoices() || []
    voice =
      voices.find((v) => v.lang === 'zh-CN') ||
      voices.find((v) => (v.lang || '').toLowerCase().startsWith('zh')) ||
      null
  }

  function bindVoices() {
    pickVoice()
    // voices 首次为空，加载完成后会触发该事件；用 addEventListener 而非
    // onvoiceschanged 赋值，避免多个实例互相覆盖
    if (!voicesBound && typeof window.speechSynthesis.addEventListener === 'function') {
      window.speechSynthesis.addEventListener('voiceschanged', pickVoice)
      voicesBound = true
    }
  }

  function setSpeaking(value) {
    if (speaking === value) return
    speaking = value
    onStateChange(value)
  }

  function next() {
    if (!enabled || speaking || !queue.length) return
    const text = queue.shift()
    if (!text.trim()) return next()

    const utter = new SpeechSynthesisUtterance(text)
    if (voice) utter.voice = voice
    utter.lang = voice?.lang || 'zh-CN'
    utter.rate = rate
    utter.pitch = pitch
    utter.volume = volume

    setSpeaking(true)
    utter.onend = () => {
      setSpeaking(false)
      next()
    }
    utter.onerror = () => {
      // 朗读失败不能中断对话：跳过这句继续
      setSpeaking(false)
      next()
    }

    try {
      window.speechSynthesis.speak(utter)
    } catch {
      setSpeaking(false)
    }
  }

  /** 喂入流式增量文本。 */
  function feed(delta) {
    if (!enabled || !delta) return
    if (!isSpeechSupported()) return
    bindVoices()
    buffer += delta
    const [sentences, rest] = splitSentences(buffer)
    buffer = rest
    if (sentences.length) {
      queue.push(...sentences)
      next()
    }
  }

  /** 本轮回答结束：把残留的尾巴读完。 */
  function flush() {
    if (!enabled || !isSpeechSupported()) return
    const tail = buffer.trim()
    buffer = ''
    if (tail) {
      queue.push(tail)
      next()
    }
  }

  /** 立即打断：停止当前朗读并清空队列（用户开口或关闭开关时调用）。 */
  function cancel() {
    queue = []
    buffer = ''
    try {
      window.speechSynthesis.cancel()
    } catch { /* 不支持则忽略 */ }
    setSpeaking(false)
  }

  function setEnabled(value) {
    enabled = !!value
    if (!enabled) cancel()
  }

  return {
    feed,
    flush,
    cancel,
    setEnabled,
    isSpeaking: () => speaking,
    isEnabled: () => enabled
  }
}
