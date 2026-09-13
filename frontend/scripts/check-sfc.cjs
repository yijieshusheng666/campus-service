/**
 * 前端语法快检：用 @vue/compiler-sfc 编译 .vue、esbuild 校验纯 JS。
 *
 * 为什么不直接 `npm run build`：本项目依赖较重，完整构建要十分钟量级；
 * 这个脚本只做「解析 + 编译」，几秒内就能抓出模板/脚本语法错误，
 * 适合改完代码随手跑一次。
 *
 * 用法：npm run check
 */
const fs = require('fs')
const path = require('path')
const { parse, compileScript, compileTemplate } = require('@vue/compiler-sfc')
const esbuild = require('esbuild')

const root = path.join(__dirname, '..')
const files = [
  'src/views/interview/InterviewChat.vue',
  'src/views/interview/InterviewList.vue',
  'src/views/interview/InterviewReport.vue',
  'src/utils/recorder.js',
  'src/utils/speech.js',
  'src/api/interview.js'
]

let failed = 0
for (const rel of files) {
  const full = path.join(root, rel)
  if (!fs.existsSync(full)) {
    console.log('MISSING', rel)
    failed++
    continue
  }
  const src = fs.readFileSync(full, 'utf-8')
  try {
    if (rel.endsWith('.vue')) {
      const { descriptor, errors } = parse(src, { filename: full })
      if (errors.length) throw new Error(errors.map((e) => e.message).join('; '))
      if (descriptor.scriptSetup) compileScript(descriptor, { id: 'x' })
      if (descriptor.template) {
        const r = compileTemplate({
          source: descriptor.template.content,
          filename: full,
          id: 'x'
        })
        if (r.errors && r.errors.length) {
          throw new Error(r.errors.map((e) => e.message || String(e)).join('; '))
        }
      }
    } else {
      esbuild.transformSync(src, { loader: 'js' })
    }
    console.log('OK   ', rel)
  } catch (e) {
    failed++
    console.log('FAIL ', rel)
    console.log('      ', e.message)
  }
}
console.log(failed ? `\n${failed} 个文件有错误` : '\n语法检查全部通过')
process.exit(failed ? 1 : 0)
