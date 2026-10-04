import type { BankQuestion, QuestionBank, QuizQuestion } from '../types'

export type UserRole = 'student' | 'admin'

export interface UserProfile {
  id: string
  name: string
  role: UserRole
  createdAt: number
}

export interface UserState {
  users: UserProfile[]
  activeUserId: string
}

export type QuestionOverride = Partial<Omit<BankQuestion, 'id'>> & { id: string }

const USERS_KEY = 'chem-quiz-users-v1'
const ACTIVE_USER_KEY = 'chem-quiz-active-user-v1'
const OVERRIDES_KEY = 'chem-quiz-question-overrides-v1'
const LEGACY_PROGRESS_KEY = 'chem-quiz-progress-v1'

export const ADMIN_CODE = import.meta.env.VITE_ADMIN_CODE || 'TTC-CHEM-2026'

function makeUserId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `user-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function writeJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Progress and local overrides are best-effort when storage is unavailable.
  }
}

function readJson<T>(key: string): T | null {
  try {
    const value = localStorage.getItem(key)
    return value ? (JSON.parse(value) as T) : null
  } catch {
    return null
  }
}

export function getInitialUserState(): UserState {
  const stored = readJson<UserState>(USERS_KEY)
  const storedActiveId = readJson<string>(ACTIVE_USER_KEY)
  const validStored = stored?.users?.length
    ? stored
    : null
  if (validStored) {
    const activeUserId = storedActiveId && validStored.users.some((user) => user.id === storedActiveId)
      ? storedActiveId
      : validStored.activeUserId
    return {
      users: validStored.users,
      activeUserId: validStored.users.some((user) => user.id === activeUserId) ? activeUserId : validStored.users[0].id,
    }
  }

  const defaultUser: UserProfile = {
    id: makeUserId(),
    name: '同学',
    role: 'student',
    createdAt: Date.now(),
  }
  const state = { users: [defaultUser], activeUserId: defaultUser.id }
  saveUserState(state)

  const legacyProgress = localStorage.getItem(LEGACY_PROGRESS_KEY)
  if (legacyProgress && !localStorage.getItem(progressStorageKey(defaultUser.id))) {
    localStorage.setItem(progressStorageKey(defaultUser.id), legacyProgress)
  }
  return state
}

export function saveUserState(state: UserState): void {
  writeJson(USERS_KEY, state)
  writeJson(ACTIVE_USER_KEY, state.activeUserId)
}

export function createUser(name: string, role: UserRole = 'student'): UserProfile {
  return {
    id: makeUserId(),
    name: name.trim() || (role === 'admin' ? '管理员' : '同学'),
    role,
    createdAt: Date.now(),
  }
}

export function progressStorageKey(userId: string): string {
  return `chem-quiz-progress-v2:${userId}`
}

export function isAdminCode(value: string): boolean {
  return value.trim() === ADMIN_CODE
}

export function loadQuestionOverrides(): Record<string, QuestionOverride> {
  return readJson<Record<string, QuestionOverride>>(OVERRIDES_KEY) ?? {}
}

export function saveQuestionOverride(question: QuizQuestion): void {
  const overrides = loadQuestionOverrides()
  overrides[question.id] = {
    id: question.id,
    type: question.type,
    contextHtml: question.contextHtml,
    promptHtml: question.promptHtml,
    plain: question.plain,
    section: question.section,
    slots: question.slots,
    options: question.options,
    multi: question.multi,
  }
  writeJson(OVERRIDES_KEY, overrides)
}

export function clearQuestionOverrides(): void {
  try {
    localStorage.removeItem(OVERRIDES_KEY)
  } catch {
    // Nothing else to do when storage is unavailable.
  }
}

export function applyQuestionOverrides(
  bank: QuestionBank,
  overrides: Record<string, QuestionOverride>,
): QuestionBank {
  if (Object.keys(overrides).length === 0) return bank
  return {
    ...bank,
    chapters: bank.chapters.map((chapter) => ({
      ...chapter,
      pages: chapter.pages.map((page) => ({
        ...page,
        questions: page.questions.map((question) => {
          const override = overrides[question.id]
          return override ? { ...question, ...override } : question
        }),
      })),
    })),
  }
}

export function updateQuestionInBank(bank: QuestionBank, question: QuizQuestion): QuestionBank {
  return {
    ...bank,
    chapters: bank.chapters.map((chapter) => ({
      ...chapter,
      pages: chapter.pages.map((page) => ({
        ...page,
        questions: page.questions.map((item) => item.id === question.id
          ? {
              ...item,
              type: question.type,
              contextHtml: question.contextHtml,
              promptHtml: question.promptHtml,
              plain: question.plain,
              section: question.section,
              slots: question.slots,
              options: question.options,
              multi: question.multi,
            }
          : item),
      })),
    })),
  }
}
