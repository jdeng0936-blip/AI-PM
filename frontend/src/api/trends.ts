import request from './request'

export const getMyScores = (days = 30) => request.get('/trends/my-scores', { params: { days } })
export const getDepartmentStats = (days = 7) => request.get('/trends/department-stats', { params: { days } })
export const getWeeklyReport = () => request.get('/trends/weekly-report')
export const askAI = (question: string) => request.post('/chat/ask', { question })
