/**
 * 分句逻辑测试：SSE 逐字流喂进来后，必须切出「完整句子」先读，
 * 把不完整的尾巴留在缓冲区等后续增量。
 *
 * 为什么要单测：分句写错会直接毁掉语音体验 —— 要么结巴（把 "96.4%" 切开），
 * 要么整段憋着不出声（长句不切分，用户等十几秒）。
 *
 * 用法：npm run check
 */
import { splitSentences } from '../src/utils/speech.js'

const cases = [
  {
    name: '两句都完整',
    input: '你好。请介绍一下自己？',
    expect: [['你好。', '请介绍一下自己？'], '']
  },
  {
    name: '尾部残留等后续增量',
    input: '你好。请自我介',
    expect: [['你好。'], '请自我介']
  },
  {
    name: '换行也视为句末',
    input: '第一行\n第二行。',
    expect: [['第一行\n', '第二行。'], '']
  },
  {
    name: '英文标点',
    input: 'Hello? Yes; ok.',
    expect: [['Hello?', ' Yes;', ' ok.'], '']
  },
  {
    name: '小数与百分比不被误切',
    input: '召回率 96.4%，效率提升 30%。',
    expect: [['召回率 96.4%，效率提升 30%。'], '']
  },
  {
    name: '长句按软停顿切开（不让用户干等）',
    input: '这是一段很长的描述，' + '甲乙丙丁戊己庚辛壬癸，'.repeat(6) + '结尾。',
    check: (sentences, rest) =>
      sentences.length >= 2 && sentences.slice(0, -1).every((s) => s.length <= 60) && rest === ''
  },
  {
    name: '空串',
    input: '',
    expect: [[], '']
  }
]

let failed = 0
for (const c of cases) {
  const [sentences, rest] = splitSentences(c.input)
  const ok = c.check
    ? c.check(sentences, rest)
    : JSON.stringify(sentences) === JSON.stringify(c.expect[0]) && rest === c.expect[1]
  if (!ok) failed++
  console.log(`${ok ? 'OK  ' : 'FAIL'} ${c.name}`)
  if (!ok) {
    console.log(`      输入: ${JSON.stringify(c.input.slice(0, 80))}`)
    console.log(`      实得: ${JSON.stringify(sentences)} + 残留 ${JSON.stringify(rest)}`)
    if (c.expect) {
      console.log(`      期望: ${JSON.stringify(c.expect[0])} + 残留 ${JSON.stringify(c.expect[1])}`)
    }
  }
}
console.log(failed ? `\n${failed} 个用例失败` : '\n分句逻辑全部通过')
process.exit(failed ? 1 : 0)
