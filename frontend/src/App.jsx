import { useState, useCallback } from 'react'
import axios from 'axios'
import BrandedHeader from './components/BrandedHeader'
import ProjectList from './components/ProjectList'
import UploadZone from './components/UploadZone'
import TierSelector from './components/TierSelector'
import FixtureSchedule from './components/FixtureSchedule'
import FloorPlanCanvas from './components/FloorPlanCanvas'

/*
  View states:
    "list"    -> ProjectList (dashboard)
    "upload"  -> New project form + UploadZone
    "results" -> Fixture schedule + plan preview
*/

export default function App() {
  const [view, setView] = useState('list')
  const [currentProject, setCurrentProject] = useState(null)
  const [tier, setTier] = useState('better')
  const [rooms, setRooms] = useState([])
  const [floorPlanId, setFloorPlanId] = useState(null)
  const [planImageUrl, setPlanImageUrl] = useState(null)
  const [tierLoading, setTierLoading] = useState(false)

  const handleNewProject = () => {
    setCurrentProject(null)
    setRooms([])
    setFloorPlanId(null)
    setPlanImageUrl(null)
    setTier('better')
    setView('upload')
  }

  const handleProjectSelect = (project) => {
    setCurrentProject(project)
    setTier(project.tier || 'better')

    // If project has floor plans with rooms, go to results
    const plans = project.floor_plans || []
    if (plans.length > 0 && plans[0].rooms && plans[0].rooms.length > 0) {
      setFloorPlanId(plans[0].id)
      setRooms(plans[0].rooms)
      // Load plan image from server for existing projects
      const plan = plans[0]
      const imgPath = `/uploads/${project.id}/${plan.original_filename}`
      setPlanImageUrl(imgPath)
      setView('results')
    } else {
      setView('upload')
    }
  }

  const handleUploadComplete = (data, projectData, imageUrl) => {
    setCurrentProject(projectData)
    setFloorPlanId(data.floor_plan_id)
    setRooms(data.rooms || [])
    setPlanImageUrl(imageUrl)
    setView('results')
  }

  const handleBackToList = () => {
    setView('list')
    setCurrentProject(null)
    setRooms([])
  }

  // Re-run lighting engine when tier changes on the results page
  const handleTierChange = useCallback(async (newTier) => {
    setTier(newTier)

    // Only re-run on the results page with a valid project and plan
    if (!currentProject?.id || !floorPlanId) return

    setTierLoading(true)
    try {
      // Update project tier
      await axios.patch(`/api/projects/${currentProject.id}`, { tier: newTier })

      // Re-parse to re-run lighting engine with new tier
      const res = await axios.post(
        `/api/projects/${currentProject.id}/plans/${floorPlanId}/parse`
      )

      setRooms(res.data.rooms || [])
      setCurrentProject(prev => ({ ...prev, tier: newTier }))
    } catch (err) {
      console.error('Failed to update tier:', err)
    } finally {
      setTierLoading(false)
    }
  }, [currentProject?.id, floorPlanId])

  return (
    <div className="min-h-screen bg-gray-50">
      <BrandedHeader
        onLogoClick={handleBackToList}
        showBack={view !== 'list'}
        onBack={handleBackToList}
      />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {view === 'list' && (
          <ProjectList
            onNewProject={handleNewProject}
            onSelectProject={handleProjectSelect}
          />
        )}

        {view === 'upload' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-semibold text-charcoal">
                New Lighting Plan
              </h2>
              <TierSelector value={tier} onChange={setTier} />
            </div>
            <UploadZone
              tier={tier}
              existingProject={currentProject}
              onComplete={handleUploadComplete}
            />
          </div>
        )}

        {view === 'results' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div>
                <h2 className="text-2xl font-semibold text-charcoal">
                  {currentProject?.name || 'Project Results'}
                </h2>
                {currentProject?.address && (
                  <p className="text-gray-500 mt-1">{currentProject.address}</p>
                )}
              </div>
              <div className="flex items-center gap-3">
                {tierLoading && (
                  <div className="w-5 h-5 border-2 border-gold border-t-transparent rounded-full animate-spin" />
                )}
                <TierSelector value={tier} onChange={handleTierChange} />
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Left: floor plan with fixture overlay */}
              <div>
                <FloorPlanCanvas imageUrl={planImageUrl} rooms={rooms} />
              </div>

              {/* Right: fixture schedule */}
              <div>
                <FixtureSchedule
                  rooms={rooms}
                  projectId={currentProject?.id}
                  tier={tier}
                />
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
