import { useEffect, useState } from 'react'
import { api } from '../api'

export default function ProgressScreen() {
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
  if (!stats) return <p>Loading progress...</p>

  if (stats.total_attempts === 0) {
    return (
      <div className="progress-screen">
        <h2>Progress</h2>
        <p>No scored answers yet — finish a training session to see your progress here.</p>
      </div>
    )
  }

  return (
    <div className="progress-screen">
      <h2>Progress</h2>
      <p>
        Average score: {stats.average_score.toFixed(1)} / 10 ({stats.total_attempts} answers)
      </p>

      <h3>Score history</h3>
      <div className="score-chart">
        {stats.score_history.map((point) => (
          <div
            key={point.attempt_id}
            className="score-bar"
            style={{ height: `${(point.score / 10) * 100}%` }}
            title={`${new Date(point.created_at).toLocaleDateString()}: ${point.score} / 10`}
          />
        ))}
      </div>

      <h3>Weakest topics</h3>
      <ul className="topic-list">
        {stats.weakest_topics.map((topic) => (
          <li key={topic.section_id}>
            <strong>{topic.section_name}</strong> — {topic.average_score.toFixed(1)} / 10 (
            {topic.attempt_count} answer{topic.attempt_count === 1 ? '' : 's'})
          </li>
        ))}
      </ul>
    </div>
  )
}
