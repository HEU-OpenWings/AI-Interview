<template>
  <div class="resume-detail-page">
    <HeaderComponent
      :title="resume?.filename || '简历详情'"
      description="左侧展示结构化简历卡片，右侧可切换查看完整简历内容。"
      :loading="loading"
    >
      <template #left>
        <a-button @click="goBack">
          <ArrowLeft :size="14" />
          返回列表
        </a-button>
      </template>

      <template #actions>
        <a-radio-group v-model:value="viewMode" size="small" class="view-mode-switch">
          <a-radio-button value="preview">简历预览</a-radio-button>
          <a-radio-button value="full">完整简历内容</a-radio-button>
        </a-radio-group>

        <a-button :loading="loading" @click="loadResumeDetail">
          <RefreshCw :size="14" />
          刷新
        </a-button>

        <a-popconfirm
          title="确认删除这份简历吗？"
          ok-text="删除"
          cancel-text="取消"
          @confirm="handleDelete"
        >
          <a-button danger :loading="deleting">
            <Trash2 :size="14" />
            删除
          </a-button>
        </a-popconfirm>
      </template>
    </HeaderComponent>

    <div class="resume-detail-content">
      <div v-if="loading" class="state-wrapper">
        <a-spin />
      </div>

      <template v-else-if="resume">
        <div v-if="viewMode === 'preview'" class="preview-shell">
          <section class="preview-hero">
            <div class="hero-info">
              <h1 class="hero-name">{{ displayName || fallbackName }}</h1>
              <div class="hero-contact">
                <span v-if="normalized.basic_info.phone" class="contact-item">
                  <Phone :size="14" />
                  {{ normalized.basic_info.phone }}
                </span>
                <span v-if="normalized.basic_info.email" class="contact-item">
                  <Mail :size="14" />
                  {{ normalized.basic_info.email }}
                </span>
                <span v-if="normalized.basic_info.github" class="contact-item">
                  <Github :size="14" />
                  {{ normalized.basic_info.github }}
                </span>
                <span v-if="normalized.basic_info.wechat" class="contact-item">
                  <span>微信</span>
                  {{ normalized.basic_info.wechat }}
                </span>
                <span v-if="normalized.basic_info.intention" class="contact-item">
                  <span>求职意向</span>
                  {{ normalized.basic_info.intention }}
                </span>
              </div>
            </div>
            <div v-if="profileImageUrl" class="hero-photo-wrap">
              <img :src="profileImageUrl" alt="简历照片" class="hero-photo" />
            </div>
          </section>

          <section class="preview-body">
            <div class="left-column">
              <div class="section-block">
                <div class="section-title">教育经历</div>
                <div v-if="normalized.education.length" class="timeline-list">
                  <article
                    v-for="(item, index) in normalized.education"
                    :key="`edu-${index}`"
                    class="timeline-item"
                  >
                    <div class="timeline-head">
                      <div class="timeline-main">{{ item.school || '未填写学校' }}</div>
                      <div v-if="formatPeriod(item.start_time, item.end_time)" class="timeline-date">
                        <CalendarDays :size="14" />
                        <span>{{ formatPeriod(item.start_time, item.end_time) }}</span>
                      </div>
                    </div>
                    <div class="timeline-sub">
                      {{ [item.major, item.degree].filter(Boolean).join(' / ') || '未填写专业/学历' }}
                    </div>
                  </article>
                </div>
                <a-empty v-else description="未提取到教育经历" />
              </div>

              <div class="section-block">
                <div class="section-title">工作经历</div>
                <div v-if="normalized.workExperience.length" class="timeline-list">
                  <article
                    v-for="(item, index) in normalized.workExperience"
                    :key="`exp-${index}`"
                    class="timeline-item"
                  >
                    <div class="timeline-head">
                      <div class="timeline-main">{{ item.company || '未填写公司' }}</div>
                      <div v-if="formatPeriod(item.start_time, item.end_time)" class="timeline-date">
                        <CalendarDays :size="14" />
                        <span>{{ formatPeriod(item.start_time, item.end_time) }}</span>
                      </div>
                    </div>
                    <div v-if="item.role" class="timeline-sub">{{ item.role }}</div>
                    <ul v-if="item.description?.length" class="desc-list">
                      <li v-for="(desc, dIndex) in item.description" :key="`exp-desc-${index}-${dIndex}`">{{ desc }}</li>
                    </ul>
                  </article>
                </div>
                <a-empty v-else description="未提取到工作经历" />
              </div>

              <div class="section-block">
                <div class="section-title">项目经历</div>
                <div v-if="normalized.projects.length" class="timeline-list">
                  <article
                    v-for="(item, index) in normalized.projects"
                    :key="`project-${index}`"
                    class="timeline-item"
                  >
                    <div class="timeline-head">
                      <div class="timeline-main">{{ item.title || '未填写项目名称' }}</div>
                      <div v-if="formatPeriod(item.start_time, item.end_time)" class="timeline-date">
                        <CalendarDays :size="14" />
                        <span>{{ formatPeriod(item.start_time, item.end_time) }}</span>
                      </div>
                    </div>
                    <div v-if="item.role" class="timeline-sub">{{ item.role }}</div>
                    <ul v-if="item.description?.length" class="desc-list">
                      <li v-for="(desc, dIndex) in item.description" :key="`project-desc-${index}-${dIndex}`">{{ desc }}</li>
                    </ul>
                  </article>
                </div>
                <a-empty v-else description="未提取到项目经历" />
              </div>



              <div class="section-block">
                <div class="section-title">校园经历</div>
                <div v-if="normalized.campusExperience.length" class="timeline-list">
                  <article
                    v-for="(item, index) in normalized.campusExperience"
                    :key="`campus-${index}`"
                    class="timeline-item"
                  >
                    <div class="timeline-head">
                      <div class="timeline-main">{{ item.company || '未填写校园组织/项目' }}</div>
                      <div v-if="formatPeriod(item.start_time, item.end_time)" class="timeline-date">
                        <CalendarDays :size="14" />
                        <span>{{ formatPeriod(item.start_time, item.end_time) }}</span>
                      </div>
                    </div>
                    <div v-if="item.role" class="timeline-sub">{{ item.role }}</div>
                    <ul v-if="item.description?.length" class="desc-list">
                      <li v-for="(desc, dIndex) in item.description" :key="`campus-desc-${index}-${dIndex}`">{{ desc }}</li>
                    </ul>
                  </article>
                </div>
                <a-empty v-else description="未提取到校园经历" />
              </div>
            </div>

            <aside class="right-column">
              <div class="section-block">
                <div class="section-title">技能</div>
                <div v-if="normalized.skills.length" class="skills-wrap">
                  <a-tag v-for="skill in normalized.skills" :key="skill" class="skill-tag">{{ skill }}</a-tag>
                </div>
                <a-empty v-else description="未提取到技能" />
              </div>

              <div class="section-block">
                <div class="section-title">获奖情况</div>
                <div v-if="normalized.awards.length" class="awards-wrap">
                  <article v-for="(award, index) in normalized.awards" :key="`award-${index}`" class="award-item">
                    <div class="award-title-row">
                      <div class="award-title">{{ award.title || '奖项' }}</div>
                      <div v-if="award.time" class="award-time">{{ award.time }}</div>
                    </div>
                    <p v-if="award.description" class="award-desc">{{ award.description }}</p>
                  </article>
                </div>
                <a-empty v-else description="未提取到获奖信息" />
              </div>
            </aside>
          </section>
        </div>

        <a-card v-else class="full-card" title="完整简历内容" :bordered="false">
          <div v-if="standardizedMarkdownContent" class="markdown-panel full-markdown flat-md-preview">
            <MdPreview
              :editorId="`resume-preview-${resume.id}`"
              :modelValue="standardizedMarkdownContent"
              previewTheme="default"
            />
          </div>
          <a-empty v-else description="当前简历暂无解析内容" />
        </a-card>
      </template>

      <div v-else class="state-wrapper">
        <a-empty description="未找到该简历" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'
import { ArrowLeft, CalendarDays, Github, Mail, Phone, RefreshCw, Trash2 } from 'lucide-vue-next'

import HeaderComponent from '@/components/HeaderComponent.vue'
import { resumeApi } from '@/apis/resume_api'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const deleting = ref(false)
const resume = ref(null)
const viewMode = ref('preview')

const fallbackName = computed(() => resume.value?.filename?.replace(/\.pdf$/i, '') || '简历')

const profileImageUrl = computed(() => {
  const markdown = String(resume.value?.markdown_content || '')
  if (!markdown) {
    return null
  }

  const markdownImageMatch = markdown.match(/!\[[^\]]*]\(([^)\s]+)(?:\s+["'][^"']*["'])?\)/i)
  if (markdownImageMatch?.[1]) {
    return markdownImageMatch[1]
  }

  const htmlImageMatch = markdown.match(/<img[^>]+src=["']([^"']+)["']/i)
  if (htmlImageMatch?.[1]) {
    return htmlImageMatch[1]
  }

  return null
})

const standardizedMarkdownContent = computed(() => {
  const raw = String(resume.value?.markdown_content || '')
  if (!raw) {
    return ''
  }

  const inferResumeName = () => {
    const fromStructured = String(
      resume.value?.structured_resume?.basic_info?.name || resume.value?.structured_resume?.name || ''
    ).trim()
    const fromFilename = String(resume.value?.filename || '').replace(/\.pdf$/i, '').trim()
    const candidate = fromStructured || fromFilename
    if (!candidate) return ''
    const cleaned = candidate.replace(/^(?:姓名|name)\s*[:：]\s*/i, '').replace(/(?:个人简历|简历|resume|cv)/gi, ' ')
    const chinese = cleaned.match(/[\u4e00-\u9fff]{2,4}/)
    if (chinese?.[0]) return chinese[0]
    const english = cleaned.match(/[A-Za-z][A-Za-z .'-]{1,39}/)
    return english?.[0]?.trim() || ''
  }

  const escapeRegex = (value) => String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const sectionLeadPattern =
    '(?:教育经历|教育背景|实习经历|工作经历|项目经历|项目经验|在校经历|校园经历|相关技能|技能|获奖情况|获奖经历|自我评价|个人评价)'
  const removeHeadingNoise = (text = '') =>
    String(text || '')
      .replace(/^\s*(?:\\?diamondsuit|textcircled\d+)\s*/i, '')
      .replace(/^\s*[■□▪●◆◇◼◾◽⬛⬜•·※★☆]+\s*/, '')
      .replace(new RegExp(`^\\s*[A-Za-z]\\s*(?=${sectionLeadPattern})`, 'i'), '')
      .replace(new RegExp(`^\\s*0+\\s*(?=${sectionLeadPattern})`, 'i'), '')
      .trim()

  let content = raw.replace(/\r\n?/g, '\n')

  content = content.replace(/<style[\s\S]*?<\/style>/gi, '')
  content = content.replace(/<script[\s\S]*?<\/script>/gi, '')
  content = content.replace(/\sstyle=(?:"[^"]*"|'[^']*')/gi, '')
  content = content.replace(/\s(?:width|height|face|size|color|align|valign|bgcolor)=(?:"[^"]*"|'[^']*')/gi, '')
  content = content.replace(/<\/?font[^>]*>/gi, '')
  content = content.replace(/&nbsp;/gi, ' ')

  content = content.replace(/<img([^>]*?)\sstyle=["'][^"']*["']([^>]*)>/gi, '<img$1$2>')
  content = content.replace(/<img([^>]*?)\swidth=["'][^"']*["']([^>]*)>/gi, '<img$1$2>')
  content = content.replace(/<img([^>]*?)\sheight=["'][^"']*["']([^>]*)>/gi, '<img$1$2>')
  content = content.replace(/<br\s*\/?>[ \t]*(<br\s*\/?>)+/gi, '<br />')
  content = content.replace(/\b1orompt\b/gi, 'prompt')
  content = content.replace(/\borompt\b/gi, 'prompt')
  content = content.replace(/\b1rompt\b/gi, 'prompt')
  content = content.replace(/结构1\s*\n+\s*prompt/gi, '结构化prompt')
  content = content.replace(/结构1(?=\s*prompt)/gi, '结构化')
  content = content.replace(/^\s*电话\s*[:：]\s*([0-9+\-\s]{7,})\s*回(?=\s*(?:微信|wechat))/gim, '电话：$1 ')
  content = content.replace(/(^|\n)(#+\s*)0+\s*(?=(?:教育|工作|项目|校园|在校|自我|个人))/g, '$1$2')

  const isProtocolNoiseLine = (line) => /(?:协议[：:；;]|鍗忚[锛?锛?]).*(?:post|get|header|delete|json|xml|xpath)/i.test(line)
  const cleanedLines = content
    .split('\n')
    .map((line) => {
      const heading = line.match(/^(\s*#{1,6}\s*)(.+)$/)
      if (heading) {
        const body = removeHeadingNoise(heading[2])
        return body ? `${heading[1]}${body}` : ''
      }
      return removeHeadingNoise(line)
    })
    .filter((line) => !isProtocolNoiseLine(line))

  const inferredName = inferResumeName()
  const topText = cleanedLines.slice(0, 14).join('\n')
  if (inferredName && !new RegExp(escapeRegex(inferredName), 'i').test(topText)) {
    cleanedLines.unshift('', `# ${inferredName}`)
  }

  content = cleanedLines.join('\n')
  content = content.replace(/\n{3,}/g, '\n\n').trim()

  return content
})
const sanitizeDisplayText = (value) => {
  const text = String(value || '')
    .replace(/\$/g, '')
    .replace(/[{}#*]+/g, '')
    .replace(/\uFFFD/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  return text
}

const stripLeadingMarker = (value) => {
  let text = sanitizeDisplayText(value || '')
  text = text.replace(/^\s*[#*•·+-]+\s*/, '')
  text = text.replace(/^\s*(?:\d+|[一二三四五六七八九十]+)\s*[.)、:：]?\s*/, '')
  return text.trim()
}

const cleanDisplayName = (value) => {
  let text = stripLeadingMarker(value || '')
  if (!text) return ''
  text = text.replace(/^(?:姓名|name)\s*[:：]\s*/i, '').trim()
  text = text
    .split(/(?:求职意向|意向岗位|工作年限|联系电话|电话|手机|邮箱|微信|github|性别|年龄|学校|出生年月|现居)/i)[0]
    .trim()
  text = text.replace(/^[#/*|·•\-\s]+/, '').trim()
  if (!text || /(简历|测试|工作经历|项目经历|教育背景|自我评价)/.test(text)) return ''
  const chinese = text.match(/[\u4e00-\u9fff]{2,4}/)
  if (chinese?.[0]) return chinese[0]
  const english = text.match(/[A-Za-z][A-Za-z .'-]{1,39}/)
  if (english?.[0]) return english[0].trim()
  return text
}

const isProtocolNoiseLine = (value) => /鍗忚[锛?锛?].*(?:post|get|header|delete|json|xml|xpath)/i.test(String(value || ''))

const isNoiseTitle = (value) => {
  const text = stripLeadingMarker(value || '')
  if (!text) return true
  if (isProtocolNoiseLine(text)) return true
  return /^(?:鑷垜璇勪环|涓汉璇勪环|涓汉鎶€鑳絴椤圭洰缁忛獙|宸ヤ綔缁忓巻|鏁欒偛鑳屾櫙|鏁欒偛缁忓巻)$/i.test(text)
}

const isSchoolLike = (value) => /(大学|学院|学校|中学|University|College|Institute)/i.test(String(value || ''))
const isMajorLike = (value) =>
  /(专业|工程|科学|管理|法学|文学|数学|统计|金融|会计|计算机|软件|人工智能)/i.test(String(value || ''))

const extractSchoolToken = (value) => {
  const text = stripLeadingMarker(value || '')
  if (!text) return ''
  const match = text.match(/([\u4e00-\u9fffA-Za-z·]{2,40}(?:大学|学院|学校|中学))/)
  return match?.[1] ? sanitizeDisplayText(match[1]) : ''
}

const extractMajorToken = (value) => {
  const text = stripLeadingMarker(value || '')
  if (!text) return ''
  const labeled = text.match(/(?:专业|主修)\s*[:：]\s*([^，,。；;\s]{2,30})/)
  if (labeled?.[1]) return sanitizeDisplayText(labeled[1])
  const match = text.match(/([\u4e00-\u9fffA-Za-z]{2,30}(?:专业|工程|科学|管理|法学|文学|数学|统计|金融|会计))/)
  return match?.[1] ? sanitizeDisplayText(match[1]) : ''
}

const extractNameFromMarkdown = (markdown) => {
  const lines = String(markdown || '')
    .split('\n')
    .map((line) => sanitizeDisplayText(line.replace(/^#{1,6}\s*/, '')))
    .filter(Boolean)
  for (const line of lines.slice(0, 12)) {
    if (/@/.test(line) || /\d{6,}/.test(line)) continue
    if (/(求职意向|工作经历|项目经历|教育背景|个人评价|个人技能)/.test(line)) continue
    const maybe = cleanDisplayName(line)
    if (maybe) return maybe
  }
  return ''
}

const extractSchoolFromMarkdown = (markdown) => {
  const lines = String(markdown || '')
    .split('\n')
    .map((line) => stripLeadingMarker(line.replace(/^#{1,6}\s*/, '')))
    .filter(Boolean)
  for (const line of lines) {
    const school = extractSchoolToken(line)
    if (school) return school
  }
  return ''
}

const extractNameFromFilename = (filename) => {
  const base = String(filename || '').replace(/\.pdf$/i, '').trim()
  if (!base) return ''
  const candidates = base.split(/[_\-\s]+/).concat([base])
  for (const candidate of candidates) {
    const m = candidate.match(/[\u4e00-\u9fff]{2,4}/)
    if (m?.[0] && !/(绠€鍘唡涓汉|浜у搧|鏍″洯|娴嬭瘯|搴旇仒|姹傝亴)/.test(m[0])) {
      return m[0]
    }
  }
  return ''
}

const isRoleLikeTitle = (value) => {
  const text = stripLeadingMarker(value || '')
  if (!text) return false
  if (/(公司|集团|科技|有限|大学|学院|学校)/.test(text)) return false
  return /(岗位|职位|实习生|工程师|经理|主管|测试|开发)/.test(text)
}

const dedupeByKey = (items = [], keyFn) => {
  const best = new Map()
  items.forEach((item) => {
    const key = keyFn(item)
    if (!key) return
    const old = best.get(key)
    const score = (item.description?.length || 0) * 10 + (item.role ? 3 : 0) + (item.start_time || item.end_time ? 2 : 0)
    const oldScore = old ? (old.description?.length || 0) * 10 + (old.role ? 3 : 0) + (old.start_time || old.end_time ? 2 : 0) : -1
    if (!old || score >= oldScore) {
      best.set(key, item)
    }
  })
  return [...best.values()]
}

const dedupeEducation = (items = []) => {
  const map = new Map()
  items.forEach((item) => {
    const school = stripLeadingMarker(item.school || '')
    const key = school || `${item.major || ''}|${item.start_time || ''}|${item.end_time || ''}`
    if (!key) return
    const existed = map.get(key)
    if (!existed) {
      map.set(key, { ...item, school })
      return
    }
    if (!existed.start_time && item.start_time) existed.start_time = item.start_time
    if (!existed.end_time && item.end_time) existed.end_time = item.end_time
    if (!existed.major && item.major) existed.major = item.major
    if (!existed.degree && item.degree) existed.degree = item.degree
  })
  return [...map.values()]
}

const mergeExperienceItems = (items = []) => {
  const merged = []
  items.forEach((item) => {
    if (isRoleLikeTitle(item.company) && item.description?.length) {
      const target = merged.find((it) => !isRoleLikeTitle(it.company))
      if (target) {
        if (!target.role) {
          target.role = item.company.replace(/^岗位\s*[:：]?\s*/, '')
        }
        target.description = [...new Set([...(target.description || []), ...(item.description || [])])]
        return
      }
    }
    merged.push({
      ...item,
      company: stripLeadingMarker(item.company || ''),
      role: stripLeadingMarker(item.role || '')
    })
  })
  return dedupeByKey(merged, (item) => `${item.company}|${item.role}|${item.start_time || ''}|${item.end_time || ''}`)
}

const normalizeProjectTitle = (value) => {
  let text = stripLeadingMarker(value || '')
  text = text.replace(/^(?:项目描述|项目简介|项目职责)\s*[:：]\s*/i, '').trim()
  if (!text) return ''
  if (isProtocolNoiseLine(text)) return ''
  if (/^(?:掌握|熟悉|了解|能够|擅长|参与)/.test(text)) return ''
  if (isNoiseTitle(text)) return ''
  return text
}

const parseProjectsFromMarkdown = (markdown) => {
  const lines = String(markdown || '')
    .split('\n')
    .map((line) => stripLeadingMarker(line.replace(/^#{1,6}\s*/, '')))
    .filter(Boolean)

  let inProject = false
  let current = null
  const projects = []

  for (const line of lines) {
    if (/(项目经历|项目经验)/.test(line)) {
      inProject = true
      continue
    }
    if (inProject && /(自我评价|个人评价|工作经历|教育背景|技能|获奖|校园经历)/.test(line)) {
      break
    }
    if (!inProject) continue
    if (isProtocolNoiseLine(line)) continue

    const range = normalizeRange(line)
    const hasDate = range.start || range.end
    if (hasDate) {
      const title = normalizeProjectTitle(
        line.replace(/((?:19|20)\d{2}|(?:19|20)[xX]{2}).*?(?:(?:19|20)\d{2}|(?:19|20)[xX]{2}|至今|现在)/, '').trim()
      )
      current = {
        title: title || '项目实践',
        role: null,
        start_time: range.start,
        end_time: range.end,
        description: []
      }
      projects.push(current)
      continue
    }

    if (current && line.length > 4 && !isNoiseTitle(line)) {
      current.description.push(line)
    }
  }

  return dedupeByKey(projects, (item) => `${item.title}|${item.start_time || ''}|${item.end_time || ''}`)
}

const extractIntentionFromText = (value) => {
  const text = sanitizeDisplayText(value || '')
  if (!text) return ''
  const match = text.match(/(?:求职意向|意向岗位)\s*[:：]?\s*([^|,，。]+)/i)
  return match?.[1] ? sanitizeDisplayText(match[1]) : ''
}

const sanitizePhoneValue = (value) => {
  const text = sanitizeDisplayText(value || '')
  if (!text) return ''
  const match = text.match(/(?:\+?86[-\s]?)?(?:1[3-9]\d{9}|\d{3,4}[-\s]?\d{7,8})/)
  const phone = match ? match[0].replace(/\s+/g, '') : text
  return phone.replace(/[鍥炲姞鑱旂郴]+$/g, '')
}

const sanitizeEmailValue = (value) => {
  const text = sanitizeDisplayText(value || '')
  if (!text) return ''
  const match = text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,10}/i)
  return match ? match[0] : text
}

const sanitizeWechatValue = (value) => {
  let text = sanitizeDisplayText(value || '')
  if (!text) return ''
  text = text.replace(/^(?:回|加|联系)?\s*(?:微信|vx|wx|v信)?\s*[:：]?\s*/i, '').trim()
  text = text.replace(/^[_-]+|[_-]+$/g, '')
  text = text.replace(/[回加联系]+$/g, '')
  if (/^(?:weixin|wechat|wx|vx)$/i.test(text)) return ''
  return text
}

const sanitizeGithubValue = (value) => {
  let text = sanitizeDisplayText(value || '')
  if (!text) return ''
  text = text.replace(/^(?:github|git)\s*[:：]?\s*/i, '').trim()
  text = text.replace(/^https?:\/\/github\.com\//i, '')
  text = text.replace(/[回加联系]+$/g, '')
  return text
}

const isAwardLikeText = (value) => {
  const text = sanitizeDisplayText(value || '')
  if (!text) return false
  return /(?:鑾峰|鑽ｈ獕|绉板彿|涓€绛夊|浜岀瓑濂東涓夌瓑濂東閲戝|閾跺|閾滃|濂栧閲憒绔炶禌|澶ц禌|璇佷功|浼樼)/i.test(text)
}

const parseDateScore = (start, end) => {
  const parseOne = (value) => {
    if (!value) return 0
    const text = String(value)
    const match = text.match(/((?:19|20)\d{2}|(?:19|20)[xX]{2})[.-]?(\d{1,2}|[xX]{1,2})?/)
    if (!match) return 0
    const y = Number(String(match[1]).replace(/[^\d]/g, '')) || 0
    const m = Number(String(match[2] || '').replace(/[^\d]/g, '')) || 0
    return y * 100 + m
  }
  return Math.max(parseOne(end), parseOne(start))
}

const sortByRecent = (items = []) => {
  return [...items].sort((a, b) => parseDateScore(b.start_time, b.end_time) - parseDateScore(a.start_time, a.end_time))
}

const isCampusExperience = (item) => {
  const full = `${item?.company || ''} ${item?.role || ''} ${(item?.description || []).join(' ')}`.toLowerCase()
  const campusKeywords = ['校园', '学校', '社团', '学生会', '协会', '俱乐部', '团委', '班级', '学院', '志愿', '宣传部']
  const workKeywords = ['公司', '集团', '科技', '有限', '实习', '全职', '兼职', '研发部', '产品部']
  const hasCampus = campusKeywords.some((k) => full.includes(k))
  const hasWork = workKeywords.some((k) => full.includes(k))
  return hasCampus && !hasWork
}

const normalizeMonth = (value) => {
  if (!value) {
    return null
  }
  const text = String(value).trim()
  if (!text) {
    return null
  }

  if (/^(至今|现在|present|current)$/i.test(text)) {
    return null
  }

  const monthMatch = text.match(/((?:19|20)\d{2}|(?:19|20)[xX]{2})\s*(?:[./-]|年)\s*(\d{1,2}|[xX]{1,2})/)
  if (monthMatch) {
    const year = String(monthMatch[1]).toLowerCase()
    const monthText = String(monthMatch[2]).toLowerCase()
    if (/x/.test(monthText)) {
      return `${year}.xx`
    }
    const month = Math.min(12, Math.max(1, Number(monthText)))
    return `${year}.${month.toString().padStart(2, '0')}`
  }

  const yearMatch = text.match(/((?:19|20)\d{2}|(?:19|20)[xX]{2})/)
  if (yearMatch) {
    return `${String(yearMatch[1]).toLowerCase()}.01`
  }

  return null
}

const normalizeRange = (raw) => {
  if (!raw) {
    return { start: null, end: null }
  }

  const text = String(raw)
  const monthMatches = [...text.matchAll(/((?:19|20)\d{2}|(?:19|20)[xX]{2})\s*(?:[./-]|年)\s*(\d{1,2}|[xX]{1,2})/g)]
  if (monthMatches.length >= 2) {
    return {
      start: normalizeMonth(monthMatches[0][0]),
      end: normalizeMonth(monthMatches[1][0])
    }
  }

  if (monthMatches.length === 1) {
    const start = normalizeMonth(monthMatches[0][0])
    const end = /(至今|现在|present|current)/i.test(text) ? null : start
    return { start, end }
  }

  const years = [...text.matchAll(/((?:19|20)\d{2}|(?:19|20)[xX]{2})/g)].map((m) => String(m[1]).toLowerCase())
  if (years.length >= 2) {
    return { start: `${years[0]}.01`, end: `${years[1]}.01` }
  }
  if (years.length === 1) {
    const start = `${years[0]}.01`
    const end = /(至今|现在|present|current)/i.test(text) ? null : start
    return { start, end }
  }

  return { start: null, end: null }
}

const toShortSentences = (items = []) => {
  const result = []
  const seen = new Set()

  items.forEach((item) => {
    const text = stripLeadingMarker(String(item || '').replace(/^[-*•·\d.)\s]+/, '').trim())
    if (!text) {
      return
    }
    if (isProtocolNoiseLine(text)) {
      return
    }

    const chunks = text.split(/[銆傦紱;]/).map((part) => part.trim()).filter(Boolean)
    ;(chunks.length ? chunks : [text]).forEach((chunk) => {
      const clean = stripLeadingMarker(chunk.replace(/\s+/g, ' ').replace(/^[锛?\s]+|[锛?銆?锛沑s]+$/g, ''))
      if (!clean || clean.length < 4 || seen.has(clean)) {
        return
      }
      seen.add(clean)
      result.push(clean)
    })
  })

  return result
}

const cleanSkills = (skills = []) => {
  const seen = new Set()
  const result = []

  skills.forEach((skill) => {
    String(skill || '')
      .split(/[銆侊紝,;锛?|]/)
      .map((token) => token.trim())
      .map((token) => token.replace(/^(鐔熸倝|鎺屾彙|浜嗚В|绮鹃€殀鎿呴暱|鍏峰|鑳藉|浣跨敤|璐熻矗|鍙備笌|浠庝簨)\s*/, ''))
      .map((token) => token.replace(/[锛?銆?;锛沑s]+$/g, ''))
      .forEach((token) => {
        if (!token || token.length > 30) {
          return
        }
        if (/^[\W_]+$/.test(token)) {
          return
        }
        const key = token.toLowerCase()
        if (seen.has(key)) {
          return
        }
        seen.add(key)
        result.push(token)
      })
  })

  return result
}

const dedupeAwards = (awards = []) => {
  const seen = new Set()
  const result = []
  awards.forEach((award) => {
    if (!award) return
    const title = sanitizeDisplayText(award.title || '')
    const description = sanitizeDisplayText(award.description || '')
    const time = sanitizeDisplayText(award.time || '')
    if (!title && !description && !time) return
    const key = `${title.replace(/\s+/g, '').toLowerCase()}|${time}`
    if (seen.has(key)) return
    seen.add(key)
    result.push({
      title: title || null,
      description: description || null,
      time: time || null
    })
  })
  return result
}

const parseAwardLine = (line) => {
  const raw = String(line || '').replace(/\s+/g, ' ').trim()
  if (!raw) {
    return null
  }

  const range = normalizeRange(raw)
  let text = raw
  const dateMatch = raw.match(/(?:19|20)\d{2}(?:\s*(?:[./-]|年)\s*\d{1,2})?(?:\s*月)?/i)
  if (dateMatch) {
    text = raw.replace(dateMatch[0], '').replace(/^[\s\-—–到至]+/, '').trim()
  }

  let title = text
  let description = null
  if (text.includes('（')) {
    ;[title, description] = text.split('（', 2)
  } else if (text.includes(':')) {
    ;[title, description] = text.split(':', 2)
  } else if (text.includes('：')) {
    ;[title, description] = text.split('：', 2)
  } else if (text.includes(' - ')) {
    ;[title, description] = text.split(' - ', 2)
  }

  return {
    title: title?.trim() || null,
    description: description?.trim() || null,
    time: range.end || range.start || null
  }
}

const normalized = computed(() => {
  const data = resume.value?.structured_resume || {}
  const markdown = String(resume.value?.markdown_content || '')
  const markdownSchoolFallback = extractSchoolFromMarkdown(markdown)
  const markdownNameFallback = extractNameFromMarkdown(markdown)

  const basicFromSchema = data.basic_info && !Array.isArray(data.basic_info) ? data.basic_info : {}
  const rawNameText = basicFromSchema.name || data.name || fallbackName.value
  const inferredIntention = extractIntentionFromText(rawNameText)

  const basic_info = {
    name: cleanDisplayName(rawNameText) || cleanDisplayName(markdownNameFallback),
    phone: sanitizePhoneValue(basicFromSchema.phone || data.phone || null),
    email: sanitizeEmailValue(basicFromSchema.email || data.email || null),
    github: sanitizeGithubValue(basicFromSchema.github || data.github || null),
    wechat: sanitizeWechatValue(basicFromSchema.wechat || data.wechat || null),
    intention: sanitizeDisplayText(basicFromSchema.intention || data.intention || inferredIntention || null)
  }
  if (basic_info.wechat && basic_info.wechat === basic_info.phone) {
    basic_info.wechat = null
  }

  const educationSource = Array.isArray(data.education) ? data.education : []
  const education = sortByRecent(dedupeEducation(educationSource
    .map((item) => {
      if (Object.prototype.hasOwnProperty.call(item, 'school')) {
        const school = stripLeadingMarker(item.school || '')
        const major = stripLeadingMarker(item.major || '')
        return {
          school: sanitizeDisplayText(school || markdownSchoolFallback || null),
          major: sanitizeDisplayText(major || null),
          degree: sanitizeDisplayText(item.degree || null),
          start_time: normalizeMonth(item.start_time),
          end_time: normalizeMonth(item.end_time)
        }
      }

      const range = normalizeRange(item.date)
      const title = stripLeadingMarker(item.title || '')
      const subtitle = stripLeadingMarker(item.subtitle || '')
      const details = Array.isArray(item.details) ? item.details.map((line) => stripLeadingMarker(line)) : []
      const school = (
        extractSchoolToken(title) ||
        extractSchoolToken(subtitle) ||
        extractSchoolToken(item.date) ||
        details.map((line) => extractSchoolToken(line)).find(Boolean) ||
        (isSchoolLike(title) ? title : '') ||
        markdownSchoolFallback
      )
      const major = (
        extractMajorToken(subtitle) ||
        extractMajorToken(title) ||
        extractMajorToken(item.date) ||
        details.map((line) => extractMajorToken(line)).find(Boolean) ||
        (isMajorLike(subtitle) ? subtitle : '') ||
        (isMajorLike(title) && title !== school ? title : '')
      )
      return {
        school: sanitizeDisplayText(school || null),
        major: sanitizeDisplayText(major || null),
        degree: null,
        start_time: range.start,
        end_time: range.end
      }
    })
    .filter((item) => item.school || item.major || item.degree || item.start_time || item.end_time)))

  const legacyExperience = Array.isArray(data.work) ? data.work : []
  const schemaExperience = Array.isArray(data.experience) ? data.experience : []
  const experienceSource = schemaExperience.length ? schemaExperience : legacyExperience
  const rawWorkExperience = experienceSource
    .map((item) => {
      if (Object.prototype.hasOwnProperty.call(item, 'company')) {
        return {
          company: stripLeadingMarker(item.company || null),
          role: stripLeadingMarker(item.role || null),
          start_time: normalizeMonth(item.start_time),
          end_time: normalizeMonth(item.end_time),
          description: toShortSentences(Array.isArray(item.description) ? item.description : [])
        }
      }

      const range = normalizeRange(item.date)
      return {
        company: stripLeadingMarker(item.title || null),
        role: stripLeadingMarker(item.subtitle || null),
        start_time: range.start,
        end_time: range.end,
        description: toShortSentences(Array.isArray(item.details) ? item.details : [])
      }
    })
    .filter((item) => !isNoiseTitle(item.company))
    .filter((item) => item.company || item.role || item.start_time || item.end_time || item.description.length)

  const campusSource = Array.isArray(data.campus_experience) ? data.campus_experience : []
  const rawCampusExperience = campusSource
    .map((item) => {
      if (Object.prototype.hasOwnProperty.call(item, 'company')) {
        return {
          company: stripLeadingMarker(item.company || null),
          role: stripLeadingMarker(item.role || null),
          start_time: normalizeMonth(item.start_time),
          end_time: normalizeMonth(item.end_time),
          description: toShortSentences(Array.isArray(item.description) ? item.description : [])
        }
      }

      const range = normalizeRange(item.date)
      return {
        company: stripLeadingMarker(item.title || null),
        role: stripLeadingMarker(item.subtitle || null),
        start_time: range.start,
        end_time: range.end,
        description: toShortSentences(Array.isArray(item.details) ? item.details : [])
      }
    })
    .filter((item) => !isNoiseTitle(item.company))
    .filter((item) => item.company || item.role || item.start_time || item.end_time || item.description.length)

  let workExperience = rawWorkExperience
  let campusExperience = rawCampusExperience
  if (!campusExperience.length) {
    campusExperience = rawWorkExperience.filter((item) => isCampusExperience(item))
    workExperience = rawWorkExperience.filter((item) => !isCampusExperience(item))
  }
  workExperience = sortByRecent(mergeExperienceItems(workExperience))
  campusExperience = sortByRecent(mergeExperienceItems(campusExperience))

  const projectSource = Array.isArray(data.projects) ? data.projects : []
  const projects = sortByRecent(projectSource
    .map((item) => {
      if (Object.prototype.hasOwnProperty.call(item, 'name') || Object.prototype.hasOwnProperty.call(item, 'start_time')) {
        return {
          title: normalizeProjectTitle(item.name || item.title || null),
          role: stripLeadingMarker(item.role || item.subtitle || null),
          start_time: normalizeMonth(item.start_time),
          end_time: normalizeMonth(item.end_time),
          description: toShortSentences(Array.isArray(item.description) ? item.description : [])
        }
      }
      const range = normalizeRange(item.date)
      return {
        title: normalizeProjectTitle(item.title || null),
        role: stripLeadingMarker(item.subtitle || null),
        start_time: range.start,
        end_time: range.end,
        description: toShortSentences(Array.isArray(item.details) ? item.details : [])
      }
    })
    .filter((item) => !isNoiseTitle(item.title))
    .filter((item) => item.title || item.role || item.start_time || item.end_time || item.description.length))
  const projectFallback = projects.length ? projects : parseProjectsFromMarkdown(markdown)

  const skillCandidates = cleanSkills(Array.isArray(data.skills) ? data.skills : [])
  const skillAsAwards = []
  const skills = skillCandidates.filter((token) => {
    if (!isAwardLikeText(token)) return true
    const parsed = parseAwardLine(token)
    if (parsed) {
      skillAsAwards.push(parsed)
    } else {
      skillAsAwards.push({ title: sanitizeDisplayText(token), description: null, time: null })
    }
    return false
  })

  const awardsSource = Array.isArray(data.awards) ? data.awards : []
  const awards = dedupeAwards([...awardsSource, ...skillAsAwards]
    .map((item) => {
      if (item && typeof item === 'object' && !Array.isArray(item)) {
        return {
          title: sanitizeDisplayText(item.title || null),
          description: sanitizeDisplayText(item.description || null),
          time: normalizeMonth(item.time)
        }
      }
      return parseAwardLine(item)
    })
    .filter((item) => item && (item.title || item.description || item.time)))

  return { basic_info, education, workExperience, campusExperience, projects: projectFallback, skills, awards }
})

const displayName = computed(() => {
  const direct = cleanDisplayName(normalized.value.basic_info.name || '')
  if (direct) {
    return direct
  }
  const fromStructured = cleanDisplayName(resume.value?.structured_resume?.name || '')
  if (fromStructured) {
    return fromStructured
  }
  const fromMarkdown = cleanDisplayName(extractNameFromMarkdown(resume.value?.markdown_content || ''))
  if (fromMarkdown) {
    return fromMarkdown
  }
  const fromFilename = cleanDisplayName(extractNameFromFilename(resume.value?.filename || fallbackName.value))
  if (fromFilename) {
    return fromFilename
  }
  return cleanDisplayName(fallbackName.value) || fallbackName.value.replace(/(?:简历测试|测试简历)\d*/gi, '').trim()
})

const loadResumeDetail = async () => {
  loading.value = true
  try {
    const data = await resumeApi.getResumeDetail(route.params.resume_id)
    resume.value = data?.resume || null
  } catch (error) {
    console.error('加载简历详情失败', error)
    message.error(error.message || '加载简历详情失败')
    resume.value = null
  } finally {
    loading.value = false
  }
}

const goBack = () => {
  router.push('/resume')
}

const handleDelete = async () => {
  if (!resume.value?.id) {
    return
  }

  try {
    deleting.value = true
    await resumeApi.deleteResume(resume.value.id)
    message.success('简历已删除')
    router.push('/resume')
  } catch (error) {
    console.error('删除简历失败', error)
    message.error(error.message || '删除简历失败')
  } finally {
    deleting.value = false
  }
}

const formatPeriod = (start, end) => {
  if (start && end) {
    return `${start} - ${end}`
  }
  if (start && !end) {
    return `${start} - 至今`
  }
  if (!start && end) {
    return end
  }
  return ''
}

onMounted(() => {
  loadResumeDetail()
})
</script>

<style scoped lang="less">
.resume-detail-page {
  min-height: 100%;
  background: var(--gray-25);
}

.resume-detail-content {
  padding: 16px;
}

.view-mode-switch {
  :deep(.ant-radio-button-wrapper) {
    min-width: 96px;
    text-align: center;
  }
}

.preview-shell {
  border: 1px solid var(--gray-200);
  border-radius: 16px;
  background: var(--gray-0);
  overflow: hidden;
}

.preview-hero {
  padding: 24px 28px;
  background: var(--main-color);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.hero-info {
  min-width: 0;
  flex: 1;
}

.hero-name {
  margin: 0;
  font-size: 38px;
  line-height: 1.1;
  font-weight: 700;
}

.hero-contact {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.contact-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

.hero-photo-wrap {
  width: 72px;
  height: 96px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.35);
  background: rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

.hero-photo {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.preview-body {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(260px, 0.8fr);
}

.left-column {
  padding: 20px 28px;
  border-right: 1px solid var(--gray-200);
}

.right-column {
  padding: 20px 22px;
}

.section-block + .section-block {
  margin-top: 22px;
}

.section-title {
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(47, 94, 234, 0.22);
  color: var(--main-color);
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
}

.timeline-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.timeline-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.timeline-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.timeline-main {
  color: var(--gray-950);
  font-size: 17px;
  font-weight: 700;
  line-height: 1.5;
}

.timeline-sub {
  color: var(--main-color);
  font-size: 15px;
  line-height: 1.6;
}

.timeline-date {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--gray-500);
  font-size: 14px;
}

.desc-list {
  margin: 2px 0 0;
  padding-left: 18px;
  color: var(--gray-800);
  line-height: 1.8;
}

.skills-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 8px;
}

.skill-tag {
  margin: 0;
  padding: 4px 10px;
  border-radius: 999px;
  color: var(--main-color);
  border-color: rgba(47, 94, 234, 0.28);
  background: rgba(47, 94, 234, 0.03);
  max-width: 100%;
  white-space: normal;
  line-height: 1.4;
  word-break: break-word;
}

.awards-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.award-item {
  padding: 12px 14px;
  border: 1px solid var(--gray-200);
  border-left: 4px solid var(--main-color);
  border-radius: 12px;
}

.award-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.award-title {
  color: var(--gray-950);
  font-weight: 600;
  line-height: 1.6;
}

.award-time {
  flex-shrink: 0;
  color: var(--gray-500);
  font-size: 13px;
}

.award-desc {
  margin: 6px 0 0;
  color: var(--gray-700);
  line-height: 1.6;
}

.full-card {
  border: 1px solid var(--gray-200);
  border-radius: 16px;

  :deep(.ant-card-head) {
    border-bottom: 1px solid var(--gray-200);
    min-height: 56px;
  }

  :deep(.ant-card-body) {
    padding: 16px;
  }
}

.markdown-panel {
  min-height: calc(100vh - 260px);

  :deep(.md-editor) {
    background: transparent;
  }

  :deep(.md-editor-preview-wrapper) {
    padding: 0;
  }
}

.full-markdown {
  :deep(.md-editor-preview) {
    color: var(--gray-900);
    font-size: 15px !important;
    line-height: 1.75 !important;
    word-break: break-word;
  }

  :deep(.md-editor-preview),
  :deep(.md-editor-preview *) {
    box-sizing: border-box;
  }

  :deep(.md-editor-preview *) {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif !important;
  }

  :deep(.md-editor-preview div),
  :deep(.md-editor-preview p),
  :deep(.md-editor-preview span),
  :deep(.md-editor-preview li),
  :deep(.md-editor-preview td),
  :deep(.md-editor-preview th) {
    font-size: inherit !important;
    line-height: inherit !important;
  }

  :deep(.md-editor-preview h1),
  :deep(.md-editor-preview h2),
  :deep(.md-editor-preview h3),
  :deep(.md-editor-preview h4),
  :deep(.md-editor-preview h5),
  :deep(.md-editor-preview h6) {
    color: var(--gray-950);
    font-weight: 700 !important;
    line-height: 1.35 !important;
    margin: 16px 0 10px !important;
  }

  :deep(.md-editor-preview h1) {
    font-size: 24px !important;
  }

  :deep(.md-editor-preview h2) {
    font-size: 20px !important;
  }

  :deep(.md-editor-preview h3) {
    font-size: 18px !important;
  }

  :deep(.md-editor-preview h4),
  :deep(.md-editor-preview h5),
  :deep(.md-editor-preview h6) {
    font-size: 16px !important;
  }

  :deep(.md-editor-preview p) {
    margin: 8px 0 !important;
  }

  :deep(.md-editor-preview ul),
  :deep(.md-editor-preview ol) {
    margin: 10px 0 !important;
    padding-left: 22px !important;
  }

  :deep(.md-editor-preview li) {
    margin: 4px 0 !important;
  }

  :deep(.md-editor-preview img) {
    display: block;
    width: auto !important;
    height: auto !important;
    max-width: 220px !important;
    max-height: 260px !important;
    margin: 12px 0 !important;
    border-radius: 8px;
    object-fit: cover;
  }

  :deep(.md-editor-preview table) {
    width: 100% !important;
    border-collapse: collapse !important;
    table-layout: fixed;
    margin: 12px 0 !important;
  }

  :deep(.md-editor-preview th),
  :deep(.md-editor-preview td) {
    border: 1px solid var(--gray-200) !important;
    padding: 8px 10px !important;
    vertical-align: top;
    word-break: break-word;
  }

  :deep(.md-editor-preview pre) {
    margin: 10px 0 !important;
    border-radius: 8px;
  }

  :deep(.md-editor-preview blockquote) {
    margin: 10px 0 !important;
    padding: 8px 12px !important;
  }
}

.state-wrapper {
  min-height: calc(100vh - 220px);
  display: flex;
  align-items: center;
  justify-content: center;
}

@media (max-width: 1200px) {
  .preview-body {
    grid-template-columns: 1fr;
  }

  .left-column {
    border-right: 0;
    border-bottom: 1px solid var(--gray-200);
  }
}

@media (max-width: 780px) {
  .hero-name {
    font-size: 28px;
  }

  .preview-hero {
    align-items: flex-start;
  }

  .hero-photo-wrap {
    width: 64px;
    height: 86px;
  }

  .left-column,
  .right-column {
    padding: 16px;
  }
}
</style>


