/**
 * WAV 编码验证：造一段 440Hz 正弦波 → 用 buildWav 封装 → 写临时文件，
 * 再用 Python 的 wave 模块交叉校验（独立实现，比自己验自己可信）。
 *
 * 为什么值得一验：WAV 头的字节序、块长度、采样率字段最容易写错，
 * 而写错的症状是「上传后上游报格式错误」，在浏览器里很难定位。
 *
 * 用法：node scripts/check-wav.mjs [输出路径]
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { buildWav } from '../src/utils/recorder.js'

const RATE = 16000
const SECONDS = 1
const total = RATE * SECONDS
const half = total / 2

// 分成两块模拟真实的分块采集
const a = new Float32Array(half)
const b = new Float32Array(half)
for (let i = 0; i < half; i++) {
  a[i] = 0.5 * Math.sin((2 * Math.PI * 440 * i) / RATE)
  b[i] = 0.5 * Math.sin((2 * Math.PI * 440 * (i + half)) / RATE)
}

const blob = buildWav([a, b], RATE)
const buf = Buffer.from(await blob.arrayBuffer())
const out = process.argv[2] || path.join(os.tmpdir(), 'wav_check.wav')
fs.writeFileSync(out, buf)

const expected = 44 + total * 2
console.log(`已生成 ${out}`)
console.log(`字节数 ${buf.length}（期望 ${expected}）${buf.length === expected ? ' ✓' : ' ✗'}`)
console.log(`MIME ${blob.type}`)
console.log(`文件头 ${buf.subarray(0, 12).toString('latin1')}`)
console.log('\n可用下面的命令进一步校验（声道/采样率/帧数/波形）：')
console.log(`python -c "import wave;w=wave.open(r'${out}');print(w.getnchannels(),w.getframerate(),w.getnframes())"`)
