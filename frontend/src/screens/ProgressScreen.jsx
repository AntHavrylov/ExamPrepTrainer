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
      <p className="chart-tooltip-date">Session #{label}</p>
      {payload.map((entry) => {
        const date = entry.payload[`${entry.dataKey}_date`]
        return (
          <p key={entry.dataKey} style={{ color: entry.color }}>
            {entry.name}: <strong>{Number(entry.value).toFixed(1)}%</strong>
            {date ? <span style={{ opacity: 0.6, fontSize: '0.85em' }}> · {date}</span> : null}
          </p>
        )
      })}
    </div>
  )
}

const HISTORY_LIMIT_OPTIONS = [5, 10, 20, 50, 0]
const RING_R = 70
const RING_CIRC = 2 * Math.PI * RING_R
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

function RingGauge({ pct }) {
  const dash = (pct / 100) * RING_CIRC
  const gap = RING_CIRC - dash
  return (
    <div className="ring-wrap">
      <svg className="ring-svg" width="172" height="172" viewBox="0 0 172 172">
        <circle cx="86" cy="86" r={RING_R} fill="none" stroke="var(--track)" strokeWidth="12" />
        <circle
          cx="86" cy="86" r={RING_R}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="12"
          strokeDasharray={`${dash} ${gap}`}
          strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 0.8s ease' }}
        />
      </svg>
      <div className="ring-center">
        <span className="ring-value">{Math.round(pct)}</span>
        <span className="ring-unit">%</span>
      </div>
    </div>
  )
}

export default function ProgressScreen({ onTrainSection }) {
  const { t } = useLanguage()
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)
  const [hiddenLines, setHiddenLines] = useState(() => new Set())
  const [historyLimit, setHistoryLimit] = useState(() => {
    const stored = localStorage.getItem('stats_history_limit')
    return stored !== null ? Number(stored) : 10
  })

  function handleHistoryLimitChange(e) {
    const val = Number(e.target.value)
    setHistoryLimit(val)
    localStorage.setItem('stats_history_limit', val)
  }

  useEffect(() => {
    api
      .getStats()
      .then(setStats)
      .catch((err) => setError(err.message))
  }, [])

  if (error)
    return (
      <p className="error" role="alert">{error}</p>
    )
  if (!stats) return <p>{t('progress.loading')}</p>

  if (stats.total_attempts === 0) {
    return (
      <div className="progress-screen">
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

  const sectionIds = Object.keys(stats.section_names).sort()
  const limit = historyLimit > 0 ? -historyLimit : undefined

  const overallSeries = history.slice(limit).map(point => ({
    score: point.score,
    date: new Date(point.created_at).toLocaleDateString(),
  }))

  const sectionSeries = {}
  sectionIds.forEach((id) => {
    sectionSeries[id] = history
      .filter(point => point.section_scores[Number(id)] != null)
      .slice(limit)
      .map(point => ({
        score: point.section_scores[Number(id)],
        date: new Date(point.created_at).toLocaleDateString(),
      }))
  })

  const maxLen = Math.max(
    overallSeries.length,
    ...Object.values(sectionSeries).map(s => s.length),
    0,
  )

  const chartData = Array.from({ length: maxLen }, (_, i) => {
    const entry = { x: i + 1 }
    const overallOffset = maxLen - overallSeries.length
    const oi = i - overallOffset
    entry.overall = oi >= 0 ? overallSeries[oi].score * 10 : null
    entry.overall_date = oi >= 0 ? overallSeries[oi].date : null
    sectionIds.forEach((id) => {
      const series = sectionSeries[id]
      const offset = maxLen - series.length
      const si = i - offset
      entry[`s${id}`] = si >= 0 ? series[si].score * 10 : null
      entry[`s${id}_date`] = si >= 0 ? series[si].date : null
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

  // Weekly activity: sum questions answered per day for the past 7 days
  const now = new Date()
  const weekActivity = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(now)
    d.setDate(now.getDate() - (6 - i))
    const count = history
      .filter((p) => {
        const pd = new Date(p.created_at)
        return (
          pd.getFullYear() === d.getFullYear() &&
          pd.getMonth() === d.getMonth() &&
          pd.getDate() === d.getDate()
        )
      })
      .reduce((sum, p) => sum + (p.attempt_count ?? 1), 0)
    return { day: DAYS[d.getDay()], count, isToday: i === 6 }
  })
  const maxWeekCount = Math.max(...weekActivity.map((d) => d.count), 1)

  // Ring gauge: average score as % (0–100)
  const avgPct = stats.average_score * 10

  return (
    <div className="progress-screen">
      <div className="stat-card-grid">
        <div className="stat-card">
          <span className="stat-card-label">{t('progress.statAverage')}</span>
          <span className="stat-card-value">{stats.average_score.toFixed(1)}<span style={{ fontSize: '16px', fontWeight: 600 }}> / 10</span></span>
          <Sparkline scores={scores} />
        </div>

        <div className="stat-card">
          <span className="stat-card-label">{t('progress.statTotal')}</span>
          <span className="stat-card-value">{stats.total_attempts}</span>
          <span className="stat-card-sub">{t('progress.dateRange', { from: firstDate, to: lastDate })}</span>
        </div>

        <div className="stat-card">
          <span className="stat-card-label">{t('progress.statLatest')}</span>
          <span className="stat-card-value">{latest.toFixed(1)}<span style={{ fontSize: '16px', fontWeight: 600 }}> / 10</span></span>
          <span className={`stat-card-sub trend-${trend}`}>{t(TREND_KEYS[trend])}</span>
        </div>

        {weakest && (
          <div className="stat-card">
            <span className="stat-card-label">{t('progress.statWeakest')}</span>
            <span className="stat-card-value">{weakest.average_score.toFixed(1)}<span style={{ fontSize: '16px', fontWeight: 600 }}> / 10</span></span>
            <span className="stat-card-sub">{weakest.section_name}</span>
          </div>
        )}
      </div>

      <div className="progress-grid">
        <div className="progress-panel">
          <h3>Weekly Activity</h3>
          <div className="weekly-chart">
            {weekActivity.map(({ day, count, isToday }) => {
              const barH = Math.max((count / maxWeekCount) * 130, count > 0 ? 16 : 0)
              return (
                <div key={day} className="weekly-bar-col">
                  {count > 0 && <span className="weekly-bar-val">{count}</span>}
                  <div
                    className={`weekly-bar ${isToday ? 'active' : 'inactive'}`}
                    style={{ height: barH || 8, opacity: count === 0 ? 0.35 : 1 }}
                  />
                  <span className="weekly-bar-day" style={{ fontWeight: isToday ? 700 : 500, color: isToday ? 'var(--accent)' : undefined }}>
                    {day}
                  </span>
                </div>
              )
            })}
          </div>
        </div>

        <div className="progress-panel ring-panel">
          <h3>Avg Score</h3>
          <RingGauge pct={avgPct} />
          <span className="ring-badge">
            {trend === 'up' ? '↑ Improving' : trend === 'down' ? '↓ Declining' : '→ Stable'}
          </span>
        </div>
      </div>

      <div className="progress-panel" style={{ marginBottom: 16 }}>
        <div className="chart-header">
          <h3>{t('progress.scoreHistory')}</h3>
          <label className="history-limit-label">
            {t('progress.historyLimit')}
            <select value={historyLimit} onChange={handleHistoryLimitChange} className="history-limit-select">
              {HISTORY_LIMIT_OPTIONS.map(n => (
                <option key={n} value={n}>
                  {n === 0 ? t('progress.historyAll') : t('progress.historyLast', { n })}
                </option>
              ))}
            </select>
          </label>
        </div>
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
          {sectionIds
            .filter(id => sectionSeries[id].length > 0)
            .map((id, idx) => {
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
              <XAxis dataKey="x" tick={{ fontSize: 11, fill: '#94a3b8' }} />
              <YAxis
                domain={[0, 100]}
                tickFormatter={v => `${v}%`}
                tick={{ fontSize: 11, fill: '#94a3b8' }}
                width={36}
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine
                y={stats.average_score * 10}
                stroke={OVERALL_COLOR}
                strokeDasharray="4 2"
                strokeOpacity={0.5}
                label={{ value: `${(stats.average_score * 10).toFixed(0)}%`, fill: '#94a3b8', fontSize: 10 }}
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
                  connectNulls={false}
                />
              )}
              {sectionIds
                .filter(id => sectionSeries[id].length > 0)
                .map((id, idx) => {
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
                      connectNulls={false}
                    />
                  )
                })}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="progress-panel">
        <h3>{t('progress.weakestTopics')}</h3>
        <div className="topic-mastery-list">
          {stats.weakest_topics.map((topic, i) => (
            <div key={topic.section_id} className="topic-mastery-row">
              <span className="topic-rank">{i + 1}</span>
              <span className="topic-name-col" title={topic.section_name}>{topic.section_name}</span>
              <div className="topic-bar-wrap">
                <div
                  className="topic-bar-fill"
                  style={{ width: `${Math.min(topic.average_score * 10, 100)}%` }}
                />
              </div>
              <span className="topic-pct">{(topic.average_score * 10).toFixed(0)}%</span>
              {onTrainSection && (
                <button
                  type="button"
                  className="topic-train-btn"
                  onClick={() => onTrainSection(topic.section_id)}
                >
                  {t('progress.trainTopic')}
                </button>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
