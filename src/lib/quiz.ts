import type {
  AttemptRecord,
  BankChapter,
  QuestionBank,
  QuizProgress,
  QuizQuestion,
} from '../types'

export const STORAGE_KEY = 'chem-quiz-progress-v1'

export const EMPTY_PROGRESS: QuizProgress = {
  attempts: {},
  wrongIds: [],
  bookmarkIds: [],
  activeDays: [],
}

export function flattenQuestions(bank: QuestionBank): QuizQuestion[] {
  return bank.chapters.flatMap((chapter) =>
    chapter.pages.flatMap((page) =>
      page.questions.map((question) => ({
        ...question,
        chapterId: chapter.id,
        chapterTitle: chapter.title,
        chapterIndex: chapter.index,
        pageNumber: page.printPage,
        questionImage: page.questionImage,
        answerImage: page.answerImage,
      })),
    ),
  )
}

export function normalizeAnswer(value: string): string {
  return value
    .toLowerCase()
    .replace(/[₀₁₂₃₄₅₆₇₈₉]/g, (character) => '₀₁₂₃₄₅₆₇₈₉'.indexOf(character).toString())
    .replace(/[⁰¹²³⁴⁵⁶⁷⁸⁹]/g, (character) => '⁰¹²³⁴⁵⁶⁷⁸⁹'.indexOf(character).toString())
    .replace(/[＋﹢]/g, '+')
    .replace(/[－﹣—–]/g, '-')
    .replace(/[（]/g, '(')
    .replace(/[）]/g, ')')
    .replace(/[，]/g, ',')
    .replace(/[；]/g, ';')
    .replace(/[×✕]/g, '×')
    .replace(/\s+/g, '')
    .replace(/[。,.，;；:：、·•]/g, '')
}

function diceCoefficient(left: string, right: string): number {
  if (left === right) return 1
  if (left.length < 2 || right.length < 2) return 0
  const pairs = new Map<string, number>()
  for (let index = 0; index < left.length - 1; index += 1) {
    const pair = left.slice(index, index + 2)
    pairs.set(pair, (pairs.get(pair) ?? 0) + 1)
  }
  let overlap = 0
  for (let index = 0; index < right.length - 1; index += 1) {
    const pair = right.slice(index, index + 2)
    const count = pairs.get(pair) ?? 0
    if (count > 0) {
      overlap += 1
      pairs.set(pair, count - 1)
    }
  }
  return (2 * overlap) / (left.length + right.length - 2)
}

function keywords(value: string): string[] {
  return value
    .split(/[，。；;,.、（）()\s:：+=\-]+/)
    .map((token) => token.trim())
    .filter((token) => token.length >= 2)
    .filter((token, index, list) => list.indexOf(token) === index)
}

export function isAnswerCorrect(
  type: QuizQuestion['type'],
  userValue: string,
  referenceValue: string,
): boolean {
  const user = normalizeAnswer(userValue)
  const reference = normalizeAnswer(referenceValue)
  if (!user) return false
  if (type === 'judge' || type === 'choice') return user === reference

  const alternatives = referenceValue
    .split(/[/／]|(?:或)|;/)
    .map(normalizeAnswer)
    .filter(Boolean)
  if (alternatives.some((answer) => answer === user)) return true

  if (reference.length <= 5) {
    if (user.includes(reference) || reference.includes(user)) return true
    return diceCoefficient(user, reference) >= 0.8
  }

  const referenceKeywords = keywords(referenceValue)
  if (referenceKeywords.length > 0) {
    const hits = referenceKeywords.filter((keyword) => user.includes(normalizeAnswer(keyword))).length
    if (hits / referenceKeywords.length >= 0.55) return true
  }

  if (user.includes(reference) || reference.includes(user)) return true
  return diceCoefficient(user, reference) >= 0.72
}

export function gradeQuestion(
  question: QuizQuestion,
  userAnswers: Record<string, string>,
): boolean {
  if (question.type === 'visual') return true
  return question.slots.every((slot) =>
    isAnswerCorrect(question.type, userAnswers[slot.id] ?? '', slot.answer),
  )
}

export function chapterStats(chapter: BankChapter, progress: QuizProgress) {
  const questions = chapter.pages.flatMap((page) => page.questions)
  const attempted = questions.filter((question) => progress.attempts[question.id])
  const correct = attempted.filter((question) => progress.attempts[question.id]?.correct)
  return {
    total: questions.length,
    attempted: attempted.length,
    correct: correct.length,
    accuracy: attempted.length ? Math.round((correct.length / attempted.length) * 100) : 0,
  }
}

export function loadProgress(): QuizProgress {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    if (!value) return EMPTY_PROGRESS
    const parsed = JSON.parse(value) as Partial<QuizProgress>
    return {
      attempts: parsed.attempts ?? {},
      wrongIds: parsed.wrongIds ?? [],
      bookmarkIds: parsed.bookmarkIds ?? [],
      activeDays: parsed.activeDays ?? [],
    }
  } catch {
    return EMPTY_PROGRESS
  }
}

export function saveProgress(progress: QuizProgress): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(progress))
}

export function applyAttempt(
  progress: QuizProgress,
  record: AttemptRecord,
): QuizProgress {
  const wrongIds = new Set(progress.wrongIds)
  if (record.correct) wrongIds.delete(record.questionId)
  else wrongIds.add(record.questionId)
  const day = new Date(record.attemptedAt).toISOString().slice(0, 10)
  const activeDays = Array.from(new Set([...progress.activeDays, day])).slice(-120)
  return {
    ...progress,
    attempts: { ...progress.attempts, [record.questionId]: record },
    wrongIds: Array.from(wrongIds),
    activeDays,
  }
}

export function toggleBookmark(progress: QuizProgress, questionId: string): QuizProgress {
  const bookmarks = new Set(progress.bookmarkIds)
  if (bookmarks.has(questionId)) bookmarks.delete(questionId)
  else bookmarks.add(questionId)
  return { ...progress, bookmarkIds: Array.from(bookmarks) }
}

export function assetUrl(path: string): string {
  const base = import.meta.env.BASE_URL || '/'
  return `${base}${path.replace(/^\//, '')}`
}

export function shuffled<T>(items: T[]): T[] {
  const copy = [...items]
  for (let index = copy.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1))
    ;[copy[index], copy[swapIndex]] = [copy[swapIndex], copy[index]]
  }
  return copy
}
