import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLanguage } from '../context/LanguageContext'

function average(numbers) {
  return numbers.reduce((sum, n) => sum + n, 0) / numbers.length
}

function Sparkline({ scores }) {
  const width = 80
  const height = 28
  const stepX = scores.length > 1 ? width / (scores.length - 1) : 0
  const coords = scores.map((score, i) => ({
    x: scores.length > 1 ? i * stepX : width / 2,
    y: height - (score / 10) * height,
  }))
  const path = coords.map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x} ${c.y}`).join(' ')

  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <path d={path} />
    </svg>
  )
}

function trendDirection(scores) {
  if (scores.length < 4) return 'unknown'
  const mid = Math.ceil(scores.length / 2)
  const delta = average(scores.slice(mid)) - average(scores.slice(0, mid))
  if (delta > 0.5) return 'up'
  if (delta < -0.5) return 'down'
  return 'flat'
}

const TREND_KEYS = {
  up: 'progress.trendUp',
  down: 'progress.trendDown',
  flat: 'progress.trendFlat',
  unknown: 'progress.trendUnknown',
}

export default function ProgressScreen() {
  const { t } = useLanguage()
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api
      .getStats()
      .then(setStats)
      .catch((err) => setError(err.message))
  }, [])

  if (error)
    return (
      <p className="error" role="alert">
        {error}
      </p>
    )
  if (!stats) return <p>{t('progress.loading')}</p>

  if (stats.total_attempts === 0) {
    return (
      <div className="progress-screen">
        <h2>{t('progress.title')}</h2>
        <p>{t('progress.empty')}</p>
      </div>
    )
  }

  const history = stats.score_history
  const scores = history.map((p) => p.score)
  const latest = scores[scores.length - 1]
  const weakest = stats.weakest_topics[0]
  const trend = trendDirection(scores)
  const firstDate = new Date(history[0].created_at).toLocaleDateString()
  const lastDate = new Date(history[history.length - 1].created_at).toLocaleDateString()

  const chartWidth = 320
  const chartHeight = 120
  const stepX = history.length > 1 ? chartWidth / (history.length - 1) : 0
  const coords = history.map((point, i) => ({
    x: history.length > 1 ? i * stepX : chartWidth / 2,
    y: chartHeight - (point.score / 10) * chartHeight,
    point,
  }))
  const linePath = coords.map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x} ${c.y}`).join(' ')
  const areaPath = `${linePath} L ${coords[coords.length - 1].x} ${chartHeight} L ${coords[0].x} ${chartHeight} Z`
  const avgY = chartHeight - (stats.average_score / 10) * chartHeight

  return (
    <div className="progress-screen">
      <h2>{t('progress.title')}</h2>

      <div className="stat-card-grid">
        <div className="stat-card">
          <span className="stat-card-label">{t('progress.statAverage')}</span>
          <span className="stat-card-value">{stats.average_score.toFixed(1)} / 10</span>
          <Sparkline scores={scores} />
        </div>

        <div className="stat-card">
          <span className="stat-card-label">{t('progress.statTotal')}</span>
          <span className="stat-card-value">{stats.total_attempts}</span>
          <span className="stat-card-sub">{t('progress.dateRange', { from: firstDate, to: lastDate })}</span>
        </div>

        <div className="stat-card">
          <span className="stat-card-label">{t('progress.statLatest')}</span>
          <span className="stat-card-value">{latest} / 10</span>
          <span className={`stat-card-sub trend-${trend}`}>{t(TREND_KEYS[trend])}</span>
        </div>

        {weakest && (
          <div className="stat-card">
            <span className="stat-card-label">{t('progress.statWeakest')}</span>
            <span className="stat-card-value">{weakest.average_score.toFixed(1)} / 10</span>
            <span className="stat-card-sub">{weakest.section_name}</span>
          </div>
        )}
      </div>

      <h3>{t('progress.scoreHistory')}</h3>
      <p className="chart-caption">{t('progress.chartCaption')}</p>
      <div className="score-chart-wrap">
        <div className="score-chart-yaxis">
          <span>10</span>
          <span>5</span>
          <span>0</span>
        </div>
        <svg
          className="score-chart"
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={t('progress.scoreHistory')}
        >
          <line className="score-chart-grid" x1="0" y1="0" x2={chartWidth} y2="0" />
          <line className="score-chart-grid" x1="0" y1={chartHeight / 2} x2={chartWidth} y2={chartHeight / 2} />
          <line className="score-chart-grid" x1="0" y1={chartHeight} x2={chartWidth} y2={chartHeight} />
          <line className="score-chart-average" x1="0" y1={avgY} x2={chartWidth} y2={avgY} />
          <path className="score-chart-area" d={areaPath} />
          <path className="score-chart-line" d={linePath} />
          {coords.map((c) => (
            <circle key={c.point.attempt_id} className="score-chart-point" cx={c.x} cy={c.y} r="2.5">
              <title>{`${new Date(c.point.created_at).toLocaleDateString()}: ${c.point.score} / 10`}</title>
            </circle>
          ))}
        </svg>
      </div>
      <div className="score-chart-xaxis">
        <span>{firstDate}</span>
        <span>{lastDate}</span>
      </div>
      <p className="chart-legend">
        <span className="chart-legend-swatch line" /> {t('progress.scoreHistory')}
        <span className="chart-legend-swatch average" /> {t('progress.chartAverageLabel', { score: stats.average_score.toFixed(1) })}
      </p>

      <h3>{t('progress.weakestTopics')}</h3>
      <ul className="topic-list">
        {stats.weakest_topics.map((topic, i) => (
          <li key={topic.section_id} className="topic-row">
            <span className="topic-rank">{i + 1}</span>
            <span className="topic-info">
              <span className="topic-name">{topic.section_name}</span>
              <span className="topic-meta">
                {topic.attempt_count} {t(topic.attempt_count === 1 ? 'progress.answerSingular' : 'progress.answerPlural')}
              </span>
            </span>
            <span className="topic-score">{topic.average_score.toFixed(1)} / 10</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
