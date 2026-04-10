import { useState } from 'react'
import BrandedHeader from './components/BrandedHeader'
import ProjectList from './components/ProjectList'
import UploadZone from './components/UploadZone'
import TierSelector from './components/TierSelector'
import FixtureSchedule from './components/FixtureSchedule'
import FloorPlanCanvas from './components/FloorPlanCanvas'
import FixturePanel from './components/FixturePanel'

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
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-semibold text-charcoal">
                  {currentProject?.name || 'Project Results'}
                </h2>
                {currentProject?.address && (
                  <p className="text-gray-500 mt-1">{currentProject.address}</p>
                )}
              </div>
              <TierSelector value={tier} onChange={setTier} />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Left: floor plan image */}
              <div className="lg:col-span-1">
                <FloorPlanCanvas imageUrl={planImageUrl} />
                <FixturePanel />
              </div>

              {/* Right: fixture schedule */}
              <div className="lg:col-span-2">
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
