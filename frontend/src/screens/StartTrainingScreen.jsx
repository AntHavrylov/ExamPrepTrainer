import { useEffect, useState } from 'react'
import { api } from '../api'

export default function StartTrainingScreen({ onStarted }) {
  const [sections, setSections] = useState([])
  const [selectedIds, setSelectedIds] = useState([])
  const [mode, setMode] = useState('mixed')
  const [format, setFormat] = useState('open_ended')
  const [difficulty, setDifficulty] = useState('medium')
  const [error, setError] = useState(null)
  const [starting, setStarting] = useState(false)

  useEffect(() => {
    api
      .listSections()
      .then(setSections)
      .catch((err) => setError(err.message))
  }, [])

  function toggleSection(id) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  async function handleStart(e) {
    e.preventDefault()
    if (selectedIds.length === 0) {
      setError('Select at least one section.')
      return
    }
    setError(null)
    setStarting(true)
    try {
      const session = await api.startSession(selectedIds, mode, format, difficulty)
      onStarted(session.id)
    } catch (err) {
      setError(err.message)
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="start-training-screen">
      <h2>Start a training session</h2>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <form onSubmit={handleStart}>
        <fieldset>
          <legend>Sections</legend>
          {sections.map((s) => (
            <label key={s.id} className="checkbox-label">
              <input
                type="checkbox"
                checked={selectedIds.includes(s.id)}
                onChange={() => toggleSection(s.id)}
              />
              {s.name}
            </label>
          ))}
          {sections.length === 0 && <p>You need at least one section with notes first.</p>}
        </fieldset>

        <label>
          Mode
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="technical">Technical</option>
            <option value="behavioral">Behavioral</option>
            <option value="mixed">Mixed</option>
          </select>
        </label>

        <label>
          Format
          <select value={format} onChange={(e) => setFormat(e.target.value)}>
            <option value="open_ended">Open-ended Q&amp;A</option>
            <option value="quiz">Multiple-choice quiz</option>
          </select>
        </label>

        <label>
          Difficulty
          <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
            <option value="easy">Easy</option>
            <option value="medium">Medium</option>
            <option value="hard">Hard</option>
          </select>
        </label>

        <button type="submit" disabled={starting}>
          {starting ? 'Starting...' : 'Start training'}
        </button>
      </form>
    </div>
  )
}
