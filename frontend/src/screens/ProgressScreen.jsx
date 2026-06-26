import { useEffect, useState } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import { api } from '../api'
import { useLanguage } from '../context/LanguageContext'

function average(numbers) {
  return numbers.reduce((sum, n) => sum + n, 0) / numbers.length
}

function trendDirection(scores) {
  if (scores.length < 4) return 'unknown'
  const mid = Math.ceil(scores.length / 2)
  const delta = average(scores.slice(mid)) - average(scores.slice(0, mid))
  if (delta > 0.5) return 'up'
  if (delta < -0.5) return 'down'
  return 'flat'
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

const TREND_KEYS = {
  up: 'progress.trendUp',
  down: 'progress.trendDown',
  flat: 'progress.trendFlat',
  unknown: 'progress.trendUnknown',
}

const SECTION_COLORS = [
  '#60a5fa', '#34d399', '#f472b6', '#fbbf24',
  '#a78bfa', '#fb923c', '#2dd4bf', '#e879f9',
]
const OVERALL_COLOR = '#818cf8'

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip-date">{label}</p>
      {payload.map((entry) => (
        <p key={entry.dataKey} style={{ color: entry.color }}>
          {entry.name}: <strong>{Number(entry.value).toFixed(1)}</strong>
        </p>
      ))}
    </div>
  )
}

export default function ProgressScreen({ onTrainSection }) {
  const { t } = useLanguage()
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)
  const [hiddenLines, setHiddenLines] = useState(() => new Set())

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

  // section_names keys are strings from JSON; sort for stable color assignment
  const sectionIds = Object.keys(stats.section_names).sort()

  const chartData = history.map((point) => {
    const entry = {
      date: new Date(point.created_at).toLocaleDateString(),
      overall: point.score,
    }
    sectionIds.forEach((id) => {
      entry[`s${id}`] = point.section_scores[Number(id)] ?? null
    })
    return entry
  })

  function toggleLine(key) {
    setHiddenLines((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

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
          <span className="stat-card-value">{latest.toFixed(1)} / 10</span>
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

      <div className="chart-toggles">
        <button
          type="button"
          className={`chart-toggle${hiddenLines.has('overall') ? ' off' : ''}`}
          style={{ '--toggle-color': OVERALL_COLOR }}
          onClick={() => toggleLine('overall')}
        >
          {t('progress.overall')}
        </button>
        {sectionIds.map((id, idx) => {
          const key = `s${id}`
          return (
            <button
              key={id}
              type="button"
              className={`chart-toggle${hiddenLines.has(key) ? ' off' : ''}`}
              style={{ '--toggle-color': SECTION_COLORS[idx % SECTION_COLORS.length] }}
              onClick={() => toggleLine(key)}
            >
              {stats.section_names[id]}
            </button>
          )
        })}
      </div>

      <div className="recharts-wrap">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#94a3b8' }} />
            <YAxis domain={[0, 10]} tick={{ fontSize: 11, fill: '#94a3b8' }} width={28} />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine
              y={stats.average_score}
              stroke={OVERALL_COLOR}
              strokeDasharray="4 2"
              strokeOpacity={0.5}
              label={{ value: stats.average_score.toFixed(1), fill: '#94a3b8', fontSize: 10 }}
            />
            {!hiddenLines.has('overall') && (
              <Line
                type="monotone"
                dataKey="overall"
                name={t('progress.overall')}
                stroke={OVERALL_COLOR}
                strokeWidth={2}
                dot={{ r: 3, fill: OVERALL_COLOR }}
                activeDot={{ r: 5 }}
                connectNulls
              />
            )}
            {sectionIds.map((id, idx) => {
              const key = `s${id}`
              if (hiddenLines.has(key)) return null
              const color = SECTION_COLORS[idx % SECTION_COLORS.length]
              return (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  name={stats.section_names[id]}
                  stroke={color}
                  strokeWidth={1.5}
                  dot={{ r: 2.5, fill: color }}
                  activeDot={{ r: 4 }}
                  connectNulls
                />
              )
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="progress-section">
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
              {onTrainSection && (
                <button
                  type="button"
                  className="btn-link topic-train-btn"
                  onClick={() => onTrainSection(topic.section_id)}
                >
                  {t('progress.trainTopic')}
                </button>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
