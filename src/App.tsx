import {
  ArrowLeft,
  BarChart3,
  BookOpenCheck,
  Bookmark,
  BookmarkCheck,
  Check,
  ChevronRight,
  CircleCheck,
  CircleX,
  House,
  Image as ImageIcon,
  Layers3,
  Library,
  Play,
  RefreshCcw,
  RotateCcw,
  Shuffle,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import './App.css'
import type {
  AttemptRecord,
  QuizProgress,
  QuizQuestion,
  QuestionBank,
} from './types'
import {
  applyAttempt,
  assetUrl,
  chapterStats,
  flattenQuestions,
  gradeQuestion,
  loadProgress,
  saveProgress,
  shuffled,
  toggleBookmark,
} from './lib/quiz'

type Tab = 'home' | 'chapters' | 'review' | 'stats'

interface PracticeSession {
  title: string
  questions: QuizQuestion[]
  index: number
}

interface ImageModalState {
  question: QuizQuestion
  mode: 'question' | 'answer'
}

const BLANK_PATTERN = /(<span class="answer-slot" data-blank-id="[^"]+"><\/span>)/g
const BLANK_ID_PATTERN = /data-blank-id="([^"]+)"/

function App() {
  const [bank, setBank] = useState<QuestionBank | null>(null)
  const [loadedAt, setLoadedAt] = useState<number | null>(null)
  const [loadError, setLoadError] = useState('')
  const [tab, setTab] = useState<Tab>('home')
  const [progress, setProgress] = useState<QuizProgress>(() => loadProgress())
  const [session, setSession] = useState<PracticeSession | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [submitted, setSubmitted] = useState(false)
  const [autoCorrect, setAutoCorrect] = useState<boolean | null>(null)
  const [imageModal, setImageModal] = useState<ImageModalState | null>(null)
  const [chapterSheet, setChapterSheet] = useState<string | null>(null)
  const [reviewMode, setReviewMode] = useState<'wrong' | 'bookmark'>('wrong')

  useEffect(() => {
    fetch(assetUrl('question-bank/bank.json'))
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json() as Promise<QuestionBank>
      })
      .then((data) => {
        setBank(data)
        setLoadedAt(Date.now())
      })
      .catch((error: unknown) => setLoadError(error instanceof Error ? error.message : '题库加载失败'))
  }, [])

  useEffect(() => {
    saveProgress(progress)
  }, [progress])

  const questions = useMemo(() => (bank ? flattenQuestions(bank) : []), [bank])
  const questionMap = useMemo(
    () => new Map(questions.map((question) => [question.id, question])),
    [questions],
  )
  const completedCount = Object.keys(progress.attempts).length
  const attempted = Object.values(progress.attempts)
  const correctCount = attempted.filter((attempt) => attempt.correct).length
  const overallAccuracy = attempted.length ? Math.round((correctCount / attempted.length) * 100) : 0
  const progressPercent = questions.length ? Math.round((completedCount / questions.length) * 100) : 0

  function commitRecord(record: AttemptRecord) {
    setProgress((current) => applyAttempt(current, record))
  }

  function startSession(title: string, source: QuizQuestion[]) {
    if (source.length === 0) return
    const firstUnanswered = source.findIndex((question) => !progress.attempts[question.id])
    const index = firstUnanswered >= 0 ? firstUnanswered : 0
    setSession({ title, questions: source, index })
    setAnswers({})
    setSubmitted(false)
    setAutoCorrect(null)
  }

  function openChapter(chapterId: string) {
    setChapterSheet(chapterId)
  }

  function continuePractice() {
    const first = questions.find((question) => !progress.attempts[question.id])
    startSession('继续刷题', first ? [first, ...questions.filter((item) => item.id !== first.id)] : questions)
  }

  function randomPractice() {
    startSession('随机练习', shuffled(questions))
  }

  function reviewPractice(mode: 'wrong' | 'bookmark') {
    const ids = mode === 'wrong' ? progress.wrongIds : progress.bookmarkIds
    const source = ids.map((id) => questionMap.get(id)).filter((item): item is QuizQuestion => Boolean(item))
    setReviewMode(mode)
    startSession(mode === 'wrong' ? '错题重练' : '收藏题', source)
  }

  function closePractice() {
    setSession(null)
    setAnswers({})
    setSubmitted(false)
    setAutoCorrect(null)
  }

  function submitCurrent() {
    if (!session) return
    const question = session.questions[session.index]
    if (question.type === 'visual') {
      setSubmitted(true)
      setAutoCorrect(null)
      return
    }
    const correct = gradeQuestion(question, answers)
    setSubmitted(true)
    setAutoCorrect(correct)
    commitRecord({
      questionId: question.id,
      chapterId: question.chapterId,
      pageNumber: question.pageNumber,
      correct,
      selfGraded: false,
      userAnswers: question.slots.map((slot) => answers[slot.id] ?? ''),
      attemptedAt: Date.now(),
    })
  }

  function selfGrade(correct: boolean) {
    if (!session) return
    const question = session.questions[session.index]
    setSubmitted(true)
    setAutoCorrect(correct)
    commitRecord({
      questionId: question.id,
      chapterId: question.chapterId,
      pageNumber: question.pageNumber,
      correct,
      selfGraded: true,
      userAnswers: question.slots.map((slot) => answers[slot.id] ?? ''),
      attemptedAt: Date.now(),
    })
  }

  function moveQuestion(direction: 1 | -1) {
    if (!session) return
    const nextIndex = session.index + direction
    if (nextIndex < 0 || nextIndex >= session.questions.length) return
    setSession({ ...session, index: nextIndex })
    setAnswers({})
    setSubmitted(false)
    setAutoCorrect(null)
  }

  function toggleCurrentBookmark() {
    if (!session) return
    const question = session.questions[session.index]
    setProgress((current) => toggleBookmark(current, question.id))
  }

  if (!bank) {
    return (
      <main className="loading-screen">
        <div className="loading-mark" aria-hidden="true">
          <svg viewBox="0 0 64 64" width="34" height="34">
            <path d="M27 13h10v12l9 20H18l9-20z" fill="#fff" />
            <path d="M22.5 41h19l3 7H19.5z" fill="#f5b05c" />
            <circle cx="30" cy="44" r="2.4" fill="#fff" fillOpacity="0.85" />
          </svg>
        </div>
        <h1>化学三轮复习</h1>
        <p>{loadError || '正在载入题库与图表...'}</p>
        {loadError && (
          <button className="primary-button" onClick={() => window.location.reload()}>
            <RefreshCcw size={18} />重新加载
          </button>
        )}
      </main>
    )
  }

  if (session) {
    const question = session.questions[session.index]
    return (
      <PracticeScreen
        session={session}
        question={question}
        answers={answers}
        submitted={submitted}
        autoCorrect={autoCorrect}
        bookmarked={progress.bookmarkIds.includes(question.id)}
        onAnswer={(slotId, value) => setAnswers((current) => ({ ...current, [slotId]: value }))}
        onSubmit={submitCurrent}
        onSelfGrade={selfGrade}
        onToggleBookmark={toggleCurrentBookmark}
        onMove={moveQuestion}
        onClose={closePractice}
        onOpenImage={(mode) => setImageModal({ question, mode })}
        imageModal={imageModal}
        onCloseImage={() => setImageModal(null)}
      />
    )
  }

  const sheetChapter = chapterSheet
    ? bank.chapters.find((chapter) => chapter.id === chapterSheet) ?? null
    : null

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">高中化学 · 三轮复习</p>
          <h1>基础知识回归</h1>
        </div>
        <div className="header-progress" aria-label={`总进度 ${progressPercent}%`}>
          <span>{progressPercent}%</span>
        </div>
      </header>

      <main className="screen-content">
        {tab === 'home' && (
          <HomeScreen
            progress={progress}
            completedCount={completedCount}
            totalCount={questions.length}
            accuracy={overallAccuracy}
            onContinue={continuePractice}
            onRandom={randomPractice}
            onOpenChapter={openChapter}
            chapters={bank.chapters}
            onReview={reviewPractice}
          />
        )}
        {tab === 'chapters' && <ChapterList bank={bank} progress={progress} onOpenChapter={openChapter} />}
        {tab === 'review' && (
          <ReviewScreen
            mode={reviewMode}
            setMode={setReviewMode}
            progress={progress}
            questionMap={questionMap}
            onStart={reviewPractice}
          />
        )}
        {tab === 'stats' && (
          <StatsScreen
            bank={bank}
            progress={progress}
            completed={completedCount}
            total={questions.length}
            accuracy={overallAccuracy}
            loadedAt={loadedAt}
          />
        )}
      </main>

      <nav className="bottom-nav" aria-label="主导航">
        <NavButton active={tab === 'home'} icon={<House size={21} />} label="首页" onClick={() => setTab('home')} />
        <NavButton active={tab === 'chapters'} icon={<Library size={21} />} label="章节" onClick={() => setTab('chapters')} />
        <NavButton active={tab === 'review'} icon={<BookOpenCheck size={21} />} label="复习" onClick={() => setTab('review')} />
        <NavButton active={tab === 'stats'} icon={<BarChart3 size={21} />} label="统计" onClick={() => setTab('stats')} />
      </nav>

      {sheetChapter && (
        <ChapterSheet
          chapter={sheetChapter}
          progress={progress}
          onClose={() => setChapterSheet(null)}
          onStart={() => {
            const chapterQuestions = sheetChapter.pages.flatMap((page) =>
              page.questions.map((question) => ({
                ...question,
                chapterId: sheetChapter.id,
                chapterTitle: sheetChapter.title,
                chapterIndex: sheetChapter.index,
                pageNumber: page.printPage,
                questionImage: page.questionImage,
                answerImage: page.answerImage,
              })),
            )
            startSession(sheetChapter.title, chapterQuestions)
            setChapterSheet(null)
          }}
        />
      )}
    </div>
  )
}

function HomeScreen({
  progress,
  completedCount,
  totalCount,
  accuracy,
  onContinue,
  onRandom,
  onOpenChapter,
  chapters,
  onReview,
}: {
  progress: QuizProgress
  completedCount: number
  totalCount: number
  accuracy: number
  onContinue: () => void
  onRandom: () => void
  onOpenChapter: (chapterId: string) => void
  chapters: QuestionBank['chapters']
  onReview: (mode: 'wrong' | 'bookmark') => void
}) {
  const recentChapters = chapters.slice(0, 4)
  return (
    <>
      <section className="focus-card">
        <div className="focus-copy">
          <span className="status-dot">进行中</span>
          <h2>{completedCount ? '接着上次继续' : '从第一章开始'}</h2>
          <p>{completedCount} / {totalCount} 题已练习 · 正确率 {accuracy}%</p>
        </div>
        <button className="round-action" onClick={onContinue} aria-label="继续刷题">
          <Play size={24} fill="currentColor" />
        </button>
      </section>

      <section className="quick-actions">
        <button onClick={onRandom}>
          <span className="quick-icon green"><Shuffle size={20} /></span>
          <span><strong>随机练习</strong><small>打散 27 章</small></span>
        </button>
        <button onClick={() => onReview('wrong')}>
          <span className="quick-icon orange"><CircleX size={20} /></span>
          <span><strong>错题重练</strong><small>{progress.wrongIds.length} 道待复习</small></span>
        </button>
        <button onClick={() => onReview('bookmark')}>
          <span className="quick-icon blue"><BookmarkCheck size={20} /></span>
          <span><strong>收藏题目</strong><small>{progress.bookmarkIds.length} 道已收藏</small></span>
        </button>
      </section>

      <section className="section-block">
        <div className="section-heading">
          <div><span className="section-kicker">CHAPTERS</span><h2>按章节练习</h2></div>
        </div>
        <div className="chapter-grid">
          {recentChapters.map((chapter) => {
            const stats = chapterStats(chapter, progress)
            return (
              <button key={chapter.id} className="chapter-card" onClick={() => onOpenChapter(chapter.id)}>
                <span className="chapter-number">{String(chapter.index).padStart(2, '0')}</span>
                <span className="chapter-card-copy">
                  <strong>{chapter.title.replace(/^[一二三四五六七八九十百]+、/, '')}</strong>
                  <small>{stats.attempted}/{stats.total} 题 · {stats.accuracy}%</small>
                </span>
                <ChevronRight size={18} />
              </button>
            )
          })}
        </div>
      </section>
    </>
  )
}

function ChapterList({ bank, progress, onOpenChapter }: { bank: QuestionBank; progress: QuizProgress; onOpenChapter: (chapterId: string) => void }) {
  return (
    <section className="section-block chapter-list-block">
      <div className="section-heading">
        <div><span className="section-kicker">27 CHAPTERS</span><h2>全部章节</h2></div>
      </div>
      <div className="chapter-grid full">
        {bank.chapters.map((chapter) => {
          const stats = chapterStats(chapter, progress)
          const percent = stats.total ? Math.round((stats.attempted / stats.total) * 100) : 0
          return (
            <button key={chapter.id} className="chapter-card" onClick={() => onOpenChapter(chapter.id)}>
              <span className="chapter-number">{String(chapter.index).padStart(2, '0')}</span>
              <span className="chapter-card-copy">
                <strong>{chapter.title.replace(/^[一二三四五六七八九十百]+、/, '')}</strong>
                <span className="mini-progress"><i style={{ width: `${percent}%` }} /></span>
                <small>{stats.attempted}/{stats.total} 题 · 正确率 {stats.accuracy}%</small>
              </span>
              <ChevronRight size={18} />
            </button>
          )
        })}
      </div>
    </section>
  )
}

function ReviewScreen({
  mode,
  setMode,
  progress,
  questionMap,
  onStart,
}: {
  mode: 'wrong' | 'bookmark'
  setMode: (mode: 'wrong' | 'bookmark') => void
  progress: QuizProgress
  questionMap: Map<string, QuizQuestion>
  onStart: (mode: 'wrong' | 'bookmark') => void
}) {
  const ids = mode === 'wrong' ? progress.wrongIds : progress.bookmarkIds
  const questions = ids.map((id) => questionMap.get(id)).filter((item): item is QuizQuestion => Boolean(item))
  return (
    <section className="section-block review-screen">
      <div className="segmented">
        <button className={mode === 'wrong' ? 'active' : ''} onClick={() => setMode('wrong')}>错题 {progress.wrongIds.length}</button>
        <button className={mode === 'bookmark' ? 'active' : ''} onClick={() => setMode('bookmark')}>收藏 {progress.bookmarkIds.length}</button>
      </div>
      <div className="review-summary">
        <span className="review-icon"><RotateCcw size={22} /></span>
        <div>
          <h2>{mode === 'wrong' ? '错题重练' : '收藏题目'}</h2>
          <p>{questions.length ? `共 ${questions.length} 道，建议先看答案再重做一遍。` : '这里还是空的。做题时把不确定的题收进来。'}</p>
        </div>
      </div>
      <button className="primary-button wide" disabled={!questions.length} onClick={() => onStart(mode)}>
        <Play size={18} />开始复习
      </button>
      <div className="question-preview-list">
        {questions.slice(0, 12).map((question) => (
          <article key={question.id}>
            <span className={`type-chip ${question.type}`}>{typeLabel(question.type)}</span>
            <p>{question.plain.replace(/\{\{blank\}\}/g, '____').slice(0, 70)}</p>
            <small>{question.chapterTitle} · P{question.pageNumber}</small>
          </article>
        ))}
      </div>
    </section>
  )
}

async function clearCachesAndUpdate() {
  try {
    if (typeof caches !== 'undefined') {
      const keys = await caches.keys()
      await Promise.all(keys.map((key) => caches.delete(key)))
    }
    if ('serviceWorker' in navigator) {
      const registrations = await navigator.serviceWorker.getRegistrations()
      await Promise.all(registrations.map((registration) => registration.update()))
    }
  } catch {
    // A failed cache purge should still reload so the shell can refetch.
  }
  window.location.reload()
}

function StatsScreen({
  bank,
  progress,
  completed,
  total,
  accuracy,
  loadedAt,
}: {
  bank: QuestionBank
  progress: QuizProgress
  completed: number
  total: number
  accuracy: number
  loadedAt: number | null
}) {
  const percent = total ? Math.round((completed / total) * 100) : 0
  const loadedLabel = loadedAt
    ? new Date(loadedAt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
    : '--'
  return (
    <section className="section-block stats-screen">
      <div className="stat-overview">
        <div className="stat-ring" style={{ '--value': `${percent * 3.6}deg` } as React.CSSProperties}><strong>{percent}%</strong><small>完成</small></div>
        <div className="stat-values">
          <div><strong>{completed}</strong><span>已练习</span></div>
          <div><strong>{accuracy}%</strong><span>正确率</span></div>
          <div><strong>{progress.wrongIds.length}</strong><span>错题</span></div>
        </div>
      </div>
      <div className="section-heading compact"><div><span className="section-kicker">BY CHAPTER</span><h2>章节掌握度</h2></div></div>
      <div className="accuracy-list">
        {bank.chapters.map((chapter) => {
          const stats = chapterStats(chapter, progress)
          return (
            <div key={chapter.id} className="accuracy-row">
              <span>{String(chapter.index).padStart(2, '0')}</span>
              <div>
                <p>{chapter.title.replace(/^[一二三四五六七八九十百]+、/, '')}</p>
                <span className="mini-progress"><i style={{ width: `${stats.attempted ? stats.accuracy : 0}%` }} /></span>
              </div>
              <strong>{stats.attempted ? `${stats.accuracy}%` : '--'}</strong>
            </div>
          )
        })}
      </div>
      <div className="activity-strip">
        <span className="section-kicker">RECENT ACTIVITY</span>
        <div className="activity-days">
          {Array.from({ length: 14 }, (_, index) => {
            const day = new Date()
            day.setDate(day.getDate() - (13 - index))
            const iso = day.toISOString().slice(0, 10)
            return <i key={iso} className={progress.activeDays.includes(iso) ? 'active' : ''} title={iso} />
          })}
        </div>
        <p>连续学习 {calculateStreak(progress.activeDays)} 天</p>
      </div>
      <div className="content-freshness">
        <div>
          <strong>题库 {total} 题 · {bank.chapters.length} 章</strong>
          <span>内容加载于 {loadedLabel}</span>
        </div>
        <button className="secondary-button" onClick={clearCachesAndUpdate}>
          <RefreshCcw size={16} />检查更新
        </button>
      </div>
    </section>
  )
}

function PracticeScreen({
  session,
  question,
  answers,
  submitted,
  autoCorrect,
  bookmarked,
  onAnswer,
  onSubmit,
  onSelfGrade,
  onToggleBookmark,
  onMove,
  onClose,
  onOpenImage,
  imageModal,
  onCloseImage,
}: {
  session: PracticeSession
  question: QuizQuestion
  answers: Record<string, string>
  submitted: boolean
  autoCorrect: boolean | null
  bookmarked: boolean
  onAnswer: (slotId: string, value: string) => void
  onSubmit: () => void
  onSelfGrade: (correct: boolean) => void
  onToggleBookmark: () => void
  onMove: (direction: 1 | -1) => void
  onClose: () => void
  onOpenImage: (mode: 'question' | 'answer') => void
  imageModal: ImageModalState | null
  onCloseImage: () => void
}) {
  const answerComplete = question.type === 'visual' || question.slots.every((slot) => (answers[slot.id] ?? '').trim())
  return (
    <div className="practice-shell">
      <header className="practice-header">
        <button className="icon-button" onClick={onClose} aria-label="退出练习"><ArrowLeft size={22} /></button>
        <div><strong>{session.title}</strong><small>{session.index + 1} / {session.questions.length} · 第 {question.pageNumber} 页</small></div>
        <button className={`icon-button ${bookmarked ? 'active' : ''}`} onClick={onToggleBookmark} aria-label="收藏"><Bookmark size={21} fill={bookmarked ? 'currentColor' : 'none'} /></button>
      </header>
      <div className="progress-line"><i style={{ width: `${((session.index + 1) / session.questions.length) * 100}%` }} /></div>

      <main className="practice-content">
        <section className="question-card">
          <div className="question-meta">
            <span className={`type-chip ${question.type}`}>{typeLabel(question.type)}</span>
            <span>{question.chapterTitle}</span>
            <span>{question.section}</span>
          </div>
          {question.contextHtml && <div className="question-context" dangerouslySetInnerHTML={{ __html: question.contextHtml }} />}
          <InteractivePrompt question={question} answers={answers} submitted={submitted} onAnswer={onAnswer} />
          <div className="source-actions">
            <button onClick={() => onOpenImage('question')}><ImageIcon size={17} />查看原题</button>
            {submitted && <button onClick={() => onOpenImage('answer')}><CircleCheck size={17} />原答案</button>}
          </div>
        </section>
        {submitted && <AnswerReview question={question} progressAnswers={answers} autoCorrect={autoCorrect} />}
      </main>

      <footer className="practice-footer">
        <button className="secondary-button" disabled={session.index === 0} onClick={() => onMove(-1)}><ArrowLeft size={18} />上一题</button>
        {!submitted ? (
          <button className="primary-button" disabled={!answerComplete} onClick={onSubmit}><Check size={18} />提交答案</button>
        ) : (
          <div className="grade-actions">
            <button onClick={() => onSelfGrade(false)}><CircleX size={17} />判错</button>
            <button onClick={() => onSelfGrade(true)}><CircleCheck size={17} />判对</button>
          </div>
        )}
        <button className="secondary-button" disabled={session.index === session.questions.length - 1} onClick={() => onMove(1)}>下一题<ChevronRight size={18} /></button>
      </footer>

      {imageModal && <ImageModal state={imageModal} onClose={onCloseImage} />}
    </div>
  )
}

function InteractivePrompt({
  question,
  answers,
  submitted,
  onAnswer,
}: {
  question: QuizQuestion
  answers: Record<string, string>
  submitted: boolean
  onAnswer: (slotId: string, value: string) => void
}) {
  if (question.type === 'visual') {
    return (
      <div className="visual-question">
        <Layers3 size={28} />
        <p>{question.plain}</p>
      </div>
    )
  }
  if (question.type === 'judge') return <JudgeInput question={question} answers={answers} submitted={submitted} onAnswer={onAnswer} />
  if (question.type === 'choice') return <ChoiceInput question={question} answers={answers} submitted={submitted} onAnswer={onAnswer} />

  const parts = question.promptHtml.split(BLANK_PATTERN)
  let blankIndex = 0
  return (
    <div className="prompt-text fill-prompt">
      {parts.map((part, index) => {
        const match = part.match(BLANK_ID_PATTERN)
        if (!match) return <span key={`${index}-${part}`} dangerouslySetInnerHTML={{ __html: part }} />
        const slot = question.slots.find((item) => item.id === match[1])
        blankIndex += 1
        if (!slot) return null
        return (
          <input
            key={slot.id}
            className={`inline-answer ${submitted ? 'answered' : ''}`}
            style={{ width: `${Math.min(180, Math.max(66, slot.width * 1.35))}px` }}
            value={answers[slot.id] ?? ''}
            disabled={submitted}
            placeholder={`空${blankIndex}`}
            onChange={(event) => onAnswer(slot.id, event.target.value)}
          />
        )
      })}
    </div>
  )
}

function JudgeInput({ question, answers, submitted, onAnswer }: { question: QuizQuestion; answers: Record<string, string>; submitted: boolean; onAnswer: (id: string, value: string) => void }) {
  const parts = question.promptHtml.split(BLANK_PATTERN)
  let index = 0
  return (
    <div className="prompt-text judge-prompt">
      {parts.map((part, partIndex) => {
        const match = part.match(BLANK_ID_PATTERN)
        if (!match) return <span key={`${partIndex}-${part}`} dangerouslySetInnerHTML={{ __html: part }} />
        const slot = question.slots.find((item) => item.id === match[1])
        if (!slot) return null
        index += 1
        return (
          <span key={slot.id} className="judge-slot">
            <span className="judge-number">{index}</span>
            <button className={answers[slot.id] === '√' ? 'selected' : ''} disabled={submitted} onClick={() => onAnswer(slot.id, '√')}>√</button>
            <button className={answers[slot.id] === '×' ? 'selected wrong' : ''} disabled={submitted} onClick={() => onAnswer(slot.id, '×')}>×</button>
          </span>
        )
      })}
    </div>
  )
}

function ChoiceInput({ question, answers, submitted, onAnswer }: { question: QuizQuestion; answers: Record<string, string>; submitted: boolean; onAnswer: (id: string, value: string) => void }) {
  const options = question.options?.length
    ? question.options
    : Array.from(new Set(question.plain.match(/[A-F](?=[.．、])/g) ?? ['A', 'B', 'C', 'D'])).map((letter) => ({
        label: letter,
        text: '',
      }))
  const singleSlot = question.slots.length === 1
  const hasOptionText = options.some((option) => option.text)
  return (
    <div className="choice-question">
      <div className="prompt-text" dangerouslySetInnerHTML={{ __html: question.promptHtml.replace(/<span class="answer-slot"[^>]*><\/span>/g, '____') }} />
      {!singleSlot && hasOptionText && (
        <ul className="choice-legend">
          {options.map((option) => (
            <li key={option.label}>
              <b>{option.label}</b>
              <span dangerouslySetInnerHTML={{ __html: option.text }} />
            </li>
          ))}
        </ul>
      )}
      {question.slots.map((slot, slotIndex) => {
        const multiple = slot.multi ?? question.multi ?? slot.answer.length > 1
        const selected = (answers[slot.id] ?? '').split('').filter(Boolean)
        const pick = (letter: string) => {
          if (!multiple) {
            onAnswer(slot.id, letter)
            return
          }
          const next = selected.includes(letter)
            ? selected.filter((item) => item !== letter)
            : [...selected, letter].sort()
          onAnswer(slot.id, next.join(''))
        }
        return (
          <div key={slot.id} className="choice-group">
            <small>{singleSlot ? (multiple ? '多选题·至少两个答案' : '单选题') : `第 ${slotIndex + 1} 空`}</small>
            {singleSlot && hasOptionText ? (
              <div className="option-list">
                {options.map((option) => (
                  <button
                    key={option.label}
                    type="button"
                    className={`option-row ${selected.includes(option.label) ? 'active' : ''}`}
                    disabled={submitted}
                    onClick={() => pick(option.label)}
                  >
                    <span className="option-label">{option.label}</span>
                    <span className="option-text" dangerouslySetInnerHTML={{ __html: option.text }} />
                  </button>
                ))}
              </div>
            ) : (
              <div className="choice-options">
                {options.map((option) => (
                  <button
                    key={option.label}
                    type="button"
                    className={selected.includes(option.label) ? 'active' : ''}
                    disabled={submitted}
                    onClick={() => pick(option.label)}
                  >{option.label}</button>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function AnswerReview({ question, progressAnswers, autoCorrect }: { question: QuizQuestion; progressAnswers: Record<string, string>; autoCorrect: boolean | null }) {
  const reviewState = autoCorrect === null ? 'pending' : autoCorrect ? 'correct' : 'wrong'
  const title = autoCorrect === null
    ? '请对照原答案完成自评'
    : autoCorrect
      ? '本轮判定：正确'
      : '本轮判定：需要再看一眼'
  const describeChoice = (value: string) => {
    const letters = value.split('').filter((item) => /[A-Z]/.test(item))
    if (question.type !== 'choice' || !question.options?.length || letters.length === 0) return value
    const texts = letters
      .map((letter) => question.options?.find((option) => option.label === letter)?.text)
      .filter((text): text is string => Boolean(text))
    return `${letters.join('、')}${texts.length ? `（${texts.join('；')}）` : ''}`
  }
  return (
    <section className={`answer-review ${reviewState}`}>
      <div className="answer-review-title">
        {autoCorrect === null ? <BookOpenCheck size={22} /> : autoCorrect ? <CircleCheck size={22} /> : <CircleX size={22} />}
        <strong>{title}</strong>
      </div>
      {question.slots.map((slot, index) => (
        <div key={slot.id} className="answer-line">
          <span>空 {index + 1}</span>
          <p>你的答案：{progressAnswers[slot.id] ? describeChoice(progressAnswers[slot.id]) : '未填写'}</p>
          <strong>参考答案：{describeChoice(slot.answer)}</strong>
        </div>
      ))}
      {question.type === 'visual' && <p className="visual-note">请在原答案图中逐项核对，再选择“判对”或“判错”。</p>}
      <p className="grading-note">
        {question.type === 'choice'
          ? '选择题按选项字母自动判分；多选题漏选、错选都算错。'
          : question.type === 'judge'
            ? '判断题按原答案的 √ / × 自动判分。'
            : '填空题按关键词判定；化学式、图表和长答案请以原答案图为准。'}
      </p>
    </section>
  )
}

function ChapterSheet({ chapter, progress, onClose, onStart }: { chapter: QuestionBank['chapters'][number]; progress: QuizProgress; onClose: () => void; onStart: () => void }) {
  const stats = chapterStats(chapter, progress)
  const percent = stats.total ? Math.round((stats.attempted / stats.total) * 100) : 0
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <section className="bottom-sheet" onClick={(event) => event.stopPropagation()}>
        <div className="sheet-handle" />
        <button className="sheet-close" onClick={onClose} aria-label="关闭"><X size={20} /></button>
        <span className="section-kicker">CHAPTER {String(chapter.index).padStart(2, '0')}</span>
        <h2>{chapter.title.replace(/^[一二三四五六七八九十百]+、/, '')}</h2>
        <div className="sheet-stats">
          <div><strong>{stats.total}</strong><span>题目</span></div>
          <div><strong>{stats.attempted}</strong><span>已做</span></div>
          <div><strong>{stats.accuracy}%</strong><span>正确率</span></div>
        </div>
        <div className="large-progress"><i style={{ width: `${percent}%` }} /></div>
        <p className="sheet-note">共 {chapter.pages.length} 页。公式、表格和装置图都可以随时打开原题核对。</p>
        <button className="primary-button wide" onClick={onStart}><Play size={18} />开始本章练习</button>
      </section>
    </div>
  )
}

function ImageModal({ state, onClose }: { state: ImageModalState; onClose: () => void }) {
  const [mode, setMode] = useState(state.mode)
  const source = mode === 'question' ? assetUrl(state.question.questionImage) : assetUrl(state.question.answerImage)
  return (
    <div className="image-modal" role="dialog" aria-modal="true">
      <header>
        <button className="icon-button" onClick={onClose} aria-label="关闭"><X size={22} /></button>
        <div className="segmented image-tabs">
          <button className={mode === 'question' ? 'active' : ''} onClick={() => setMode('question')}>原题</button>
          <button className={mode === 'answer' ? 'active' : ''} onClick={() => setMode('answer')}>答案</button>
        </div>
        <span>P{state.question.pageNumber}</span>
      </header>
      <div className="image-stage"><img src={source} alt={mode === 'question' ? '原题截图' : '答案截图'} /></div>
    </div>
  )
}

function NavButton({ active, icon, label, onClick }: { active: boolean; icon: React.ReactNode; label: string; onClick: () => void }) {
  return <button className={active ? 'active' : ''} onClick={onClick} aria-label={label}>{icon}<span>{label}</span></button>
}

function typeLabel(type: QuizQuestion['type']): string {
  if (type === 'judge') return '判断题'
  if (type === 'choice') return '选择题'
  if (type === 'visual') return '原图题'
  return '填空题'
}

function calculateStreak(days: string[]): number {
  const set = new Set(days)
  let count = 0
  const cursor = new Date()
  while (set.has(cursor.toISOString().slice(0, 10))) {
    count += 1
    cursor.setDate(cursor.getDate() - 1)
  }
  return count
}

export default App
