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
              <h1 class="hero-name">{{ normalized.basic_info.name || fallbackName }}</h1>
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
                      {{ [item.major, item.degree].filter(Boolean).join(' · ') || '未填写专业/学历' }}
                    </div>
                  </article>
                </div>
                <a-empty v-else description="未提取到教育经历" />
              </div>

              <div class="section-block">
                <div class="section-title">工作经历</div>
                <div v-if="normalized.experience.length" class="timeline-list">
                  <article
                    v-for="(item, index) in normalized.experience"
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

  content = content.replace(/\n{3,}/g, '\n\n').trim()

  return content
})

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

  const monthMatch = text.match(/((?:19|20)\d{2})\s*(?:[./-]|年)\s*(\d{1,2})/)
  if (monthMatch) {
    const year = Number(monthMatch[1])
    const month = Math.min(12, Math.max(1, Number(monthMatch[2])))
    return `${year.toString().padStart(4, '0')}.${month.toString().padStart(2, '0')}`
  }

  const yearMatch = text.match(/((?:19|20)\d{2})/)
  if (yearMatch) {
    return `${yearMatch[1]}.01`
  }

  return null
}

const normalizeRange = (raw) => {
  if (!raw) {
    return { start: null, end: null }
  }

  const text = String(raw)
  const monthMatches = [...text.matchAll(/((?:19|20)\d{2})\s*(?:[./-]|年)\s*(\d{1,2})/g)]
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

  const years = [...text.matchAll(/((?:19|20)\d{2})/g)].map((m) => m[1])
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
    const text = String(item || '').replace(/^[-*•·\d.)\s]+/, '').trim()
    if (!text) {
      return
    }

    const chunks = text.split(/[。；;]/).map((part) => part.trim()).filter(Boolean)
    ;(chunks.length ? chunks : [text]).forEach((chunk) => {
      const clean = chunk.replace(/\s+/g, ' ').replace(/^[，,\s]+|[，,。;；\s]+$/g, '')
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
      .split(/[、，,;；/|]/)
      .map((token) => token.trim())
      .map((token) => token.replace(/^(熟悉|掌握|了解|精通|擅长|具备|能够|使用|负责|参与|从事)\s*/, ''))
      .map((token) => token.replace(/[：:。.;；\s]+$/g, ''))
      .forEach((token) => {
        if (!token || token.length > 30) {
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

const parseAwardLine = (line) => {
  const raw = String(line || '').replace(/\s+/g, ' ').trim()
  if (!raw) {
    return null
  }

  const range = normalizeRange(raw)
  let text = raw
  const dateMatch = raw.match(/(?:19|20)\d{2}(?:\s*(?:[./-]|年)\s*\d{1,2})?(?:\s*月)?/)
  if (dateMatch) {
    text = raw.replace(dateMatch[0], '').replace(/^[\s\-–—~到至]+/, '').trim()
  }

  let title = text
  let description = null
  if (text.includes('：')) {
    ;[title, description] = text.split('：', 2)
  } else if (text.includes(':')) {
    ;[title, description] = text.split(':', 2)
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

  const basicFromSchema = data.basic_info && !Array.isArray(data.basic_info) ? data.basic_info : {}
  const basicFromLegacy = data.basic_info && !Array.isArray(data.basic_info) ? data.basic_info : {}

  const basic_info = {
    name: basicFromSchema.name || data.name || fallbackName.value,
    phone: basicFromSchema.phone || data.phone || null,
    email: basicFromSchema.email || data.email || null,
    github: basicFromSchema.github || basicFromLegacy.github || null
  }

  const educationSource = Array.isArray(data.education) ? data.education : []
  const education = educationSource
    .map((item) => {
      if (Object.prototype.hasOwnProperty.call(item, 'school')) {
        return {
          school: item.school || null,
          major: item.major || null,
          degree: item.degree || null,
          start_time: normalizeMonth(item.start_time),
          end_time: normalizeMonth(item.end_time)
        }
      }

      const range = normalizeRange(item.date)
      return {
        school: item.title || null,
        major: item.subtitle || null,
        degree: null,
        start_time: range.start,
        end_time: range.end
      }
    })
    .filter((item) => item.school || item.major || item.degree || item.start_time || item.end_time)

  const legacyExperience = Array.isArray(data.work) ? data.work : []
  const schemaExperience = Array.isArray(data.experience) ? data.experience : []
  const experienceSource = schemaExperience.length ? schemaExperience : legacyExperience
  const experience = experienceSource
    .map((item) => {
      if (Object.prototype.hasOwnProperty.call(item, 'company')) {
        return {
          company: item.company || null,
          role: item.role || null,
          start_time: normalizeMonth(item.start_time),
          end_time: normalizeMonth(item.end_time),
          description: toShortSentences(Array.isArray(item.description) ? item.description : [])
        }
      }

      const range = normalizeRange(item.date)
      return {
        company: item.title || null,
        role: item.subtitle || null,
        start_time: range.start,
        end_time: range.end,
        description: toShortSentences(Array.isArray(item.details) ? item.details : [])
      }
    })
    .filter((item) => item.company || item.role || item.start_time || item.end_time || item.description.length)

  const projectSource = Array.isArray(data.projects) ? data.projects : []
  const projects = projectSource
    .map((item) => {
      const range = normalizeRange(item.date)
      return {
        title: item.title || null,
        role: item.subtitle || null,
        start_time: range.start,
        end_time: range.end,
        description: toShortSentences(Array.isArray(item.details) ? item.details : [])
      }
    })
    .filter((item) => item.title || item.role || item.start_time || item.end_time || item.description.length)

  const skills = cleanSkills(Array.isArray(data.skills) ? data.skills : [])

  const awardsSource = Array.isArray(data.awards) ? data.awards : []
  const awards = awardsSource
    .map((item) => {
      if (item && typeof item === 'object' && !Array.isArray(item)) {
        return {
          title: item.title || null,
          description: item.description || null,
          time: normalizeMonth(item.time)
        }
      }
      return parseAwardLine(item)
    })
    .filter((item) => item && (item.title || item.description || item.time))

  return { basic_info, education, experience, projects, skills, awards }
})

const loadResumeDetail = async () => {
  loading.value = true
  try {
    const data = await resumeApi.getResumeDetail(route.params.resume_id)
    resume.value = data?.resume || null
  } catch (error) {
    console.error('加载简历详情失败:', error)
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
    console.error('删除简历失败:', error)
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
