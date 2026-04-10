import { useState, useEffect } from 'react'
import axios from 'axios'

const STATUS_COLORS = {
  draft: 'bg-gray-100 text-gray-600',
  parsing: 'bg-yellow-100 text-yellow-700',
  parsed: 'bg-blue-100 text-blue-700',
  assigned: 'bg-green-100 text-green-700',
  exported: 'bg-gold/20 text-gold-dark',
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export default function ProjectList({ onNewProject, onSelectProject }) {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadProjects()
  }, [])

  const loadProjects = async () => {
    try {
      const res = await axios.get('/api/projects')
      setProjects(res.data)
    } catch (err) {
      console.error('Failed to load projects:', err)
      setError('Failed to load projects.')
    } finally {
      setLoading(false)
    }
  }

  const handleSelect = async (project) => {
    // Fetch full project with rooms and fixtures
    try {
      const res = await axios.get(`/api/projects/${project.id}`)
      onSelectProject(res.data)
    } catch (err) {
      console.error('Failed to load project:', err)
      alert('Failed to load project details.')
    }
  }

  if (loading) {
    return (
      <div className="text-center py-12 text-gray-500">
        Loading projects...
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold text-charcoal">Projects</h2>
        <button
          onClick={onNewProject}
          className="bg-gold hover:bg-gold-dark text-charcoal font-semibold px-5 py-2.5 rounded-md transition-colors text-sm"
        >
          + New Project
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm mb-4">
          {error}
        </div>
      )}

      {projects.length === 0 ? (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <svg className="w-16 h-16 mx-auto text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
          <p className="text-gray-500 text-lg">No projects yet</p>
          <p className="text-gray-400 text-sm mt-1">
            Create your first lighting plan to get started.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project) => (
            <button
              key={project.id}
              onClick={() => handleSelect(project)}
              className="bg-white rounded-lg border border-gray-200 p-5 text-left hover:border-gold hover:shadow-sm transition-all"
            >
              <div className="flex items-start justify-between mb-2">
                <h3 className="font-semibold text-charcoal truncate pr-2">
                  {project.name}
                </h3>
                <span className={`text-xs px-2 py-0.5 rounded-full whitespace-nowrap ${STATUS_COLORS[project.status] || STATUS_COLORS.draft}`}>
                  {project.status}
                </span>
              </div>
              {project.address && (
                <p className="text-sm text-gray-500 truncate">{project.address}</p>
              )}
              <p className="text-xs text-gray-400 mt-2">
                {formatDate(project.updated_at)}
              </p>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
