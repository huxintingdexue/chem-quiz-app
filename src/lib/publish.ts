import type { QuestionBank } from '../types'

const REPOSITORY = 'huxintingdexue/chem-quiz-app'
const BANK_PATH = 'public/question-bank/bank.json'
const BRANCH = 'main'

function encodeBase64(value: string): string {
  const bytes = new TextEncoder().encode(value)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary)
}

export async function publishQuestionBank(
  bank: QuestionBank,
  token: string,
  questionId: string,
): Promise<{ commitUrl: string }> {
  const headers = {
    Accept: 'application/vnd.github+json',
    Authorization: `Bearer ${token.trim()}`,
    'X-GitHub-Api-Version': '2022-11-28',
  }
  const fileUrl = `https://api.github.com/repos/${REPOSITORY}/contents/${BANK_PATH}?ref=${BRANCH}`
  const fileResponse = await fetch(fileUrl, { headers })
  if (!fileResponse.ok) throw new Error(`读取 GitHub 题库失败（${fileResponse.status}）`)
  const file = await fileResponse.json() as { sha?: string }
  if (!file.sha) throw new Error('未取得 GitHub 题库版本号')

  const response = await fetch(`https://api.github.com/repos/${REPOSITORY}/contents/${BANK_PATH}`, {
    method: 'PUT',
    headers: {
      ...headers,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message: `Update question ${questionId}`,
      content: encodeBase64(JSON.stringify(bank)),
      sha: file.sha,
      branch: BRANCH,
    }),
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`同步 GitHub 失败（${response.status}）${detail ? `：${detail.slice(0, 120)}` : ''}`)
  }
  const result = await response.json() as { commit?: { html_url?: string } }
  return { commitUrl: result.commit?.html_url ?? '' }
}
