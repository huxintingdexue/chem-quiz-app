export type QuestionType = 'fill' | 'judge' | 'choice' | 'visual'

export interface AnswerSlot {
  id: string
  answer: string
  x0: number
  x1: number
  width: number
  kind: QuestionType
}

export interface BankQuestion {
  id: string
  type: QuestionType
  contextHtml: string
  promptHtml: string
  plain: string
  section: string
  slots: AnswerSlot[]
}

export interface BankPage {
  id: string
  printPage: number
  questionImage: string
  answerImage: string
  questions: BankQuestion[]
}

export interface BankChapter {
  id: string
  index: number
  title: string
  pages: BankPage[]
}

export interface QuestionBank {
  title: string
  source: string
  chapters: BankChapter[]
}

export interface QuizQuestion extends BankQuestion {
  chapterId: string
  chapterTitle: string
  chapterIndex: number
  pageNumber: number
  questionImage: string
  answerImage: string
}

export interface AttemptRecord {
  questionId: string
  chapterId: string
  pageNumber: number
  correct: boolean
  selfGraded: boolean
  userAnswers: string[]
  attemptedAt: number
}

export interface QuizProgress {
  attempts: Record<string, AttemptRecord>
  wrongIds: string[]
  bookmarkIds: string[]
  activeDays: string[]
}
