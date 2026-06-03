import { useState, useEffect } from 'react'
import axios from 'axios'

const STATUS_STYLES = {
  draft: 'bg-rule/50 text-hint',
  parsing: 'bg-gold/10 text-gold-dark',
  parsed: 'bg-gold/10 text-gold-dark',
  assigned: 'bg-charcoal/10 text-charcoal',
  exported: 'bg-charcoal/10 text-charcoal',
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function ProjectList({ onNewProject, onNewFloorPlan, onSelectProject }) {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => { loadProjects() }, [])

  const loadProjects = async () => {
    try {
      const res = await axios.get('/api/projects')
      setProjects(res.data || [])
    } catch (err) {
      setError('Failed to load projects')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-6 h-6 border-2 border-gold/30 border-t-gold rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="text-[10px] uppercase tracking-[0.28em] text-gold font-medium mb-1">Dashboard</div>
          <h2 className="font-serif text-3xl font-light text-charcoal">Projects</h2>
        </div>
        <div className="flex items-center gap-4">
          <button
            onClick={onNewProject}
            className="px-5 py-2.5 bg-charcoal text-white text-[10px] uppercase tracking-[0.14em] font-medium rounded-sm hover:bg-charcoal-dark transition-colors"
          >
            + New Estimate
          </button>
          {onNewFloorPlan && (
            <button
              onClick={onNewFloorPlan}
              className="text-hint hover:text-charcoal text-[11px] uppercase tracking-[0.1em] transition-colors font-light"
            >
              Upload Floor Plan
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-md p-4 text-red-700 text-sm mb-6">
          {error}
        </div>
      )}

      {projects.length === 0 && !error ? (
        <div className="bg-white border border-rule rounded-md p-12 text-center">
          <div className="font-serif text-2xl text-muted font-light italic mb-3">No projects yet</div>
          <p className="text-hint text-sm font-light mb-6">Create your first lighting estimate to get started.</p>
          <button
            onClick={onNewProject}
            className="px-6 py-2.5 bg-charcoal text-white text-[10px] uppercase tracking-[0.14em] font-medium rounded-sm hover:bg-charcoal-dark transition-colors"
          >
            + New Estimate
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map(project => (
            <button
              key={project.id}
              onClick={() => onSelectProject(project)}
              className="bg-white border border-rule rounded-md p-5 text-left hover:border-gold/60 hover:shadow-sm transition-all group"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="font-serif text-lg text-charcoal group-hover:text-charcoal-dark transition-colors leading-tight">
                  {project.name}
                </div>
                <span className={`text-[9px] uppercase tracking-[0.14em] px-2 py-0.5 rounded-sm font-medium flex-shrink-0 ml-2 ${
                  STATUS_STYLES[project.status] || STATUS_STYLES.draft
                }`}>
                  {project.status}
                </span>
              </div>
              {project.address && (
                <p className="text-xs text-hint font-light mb-2">{project.address}</p>
              )}
              <div className="flex items-center justify-between mt-3 pt-3 border-t border-rule/50">
                <span className="text-[10px] text-hint font-light">{formatDate(project.created_at)}</span>
                <span className="text-[9px] uppercase tracking-[0.14em] text-gold font-medium">
                  {project.tier}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
