import { useState, useCallback } from 'react'
import axios from 'axios'
import BrandedHeader from './components/BrandedHeader'
import ProjectList from './components/ProjectList'
import UploadZone from './components/UploadZone'
import TierSelector from './components/TierSelector'
import FixtureSchedule from './components/FixtureSchedule'
import FloorPlanCanvas from './components/FloorPlanCanvas'
import EstimateBuilder from './components/EstimateBuilder'
import EstimateSummaryCard from './components/EstimateSummaryCard'

/*
  View states:
    "list"     -> ProjectList (dashboard)
    "estimate" -> EstimateBuilder (form-driven, primary flow)
    "upload"   -> Legacy floor plan upload flow
    "results"  -> Fixture schedule + summary or plan overlay
*/

export default function App() {
  const [view, setView] = useState('list')
  const [currentProject, setCurrentProject] = useState(null)
  const [tier, setTier] = useState('better')
  const [rooms, setRooms] = useState([])
  const [floorPlanId, setFloorPlanId] = useState(null)
  const [planImageUrl, setPlanImageUrl] = useState(null)
  const [schematicData, setSchematicData] = useState(null)
  const [tierLoading, setTierLoading] = useState(false)
  const [projectMode, setProjectMode] = useState('estimate')
  const [estimateSummary, setEstimateSummary] = useState(null)
  const [tierPcts, setTierPcts] = useState({ good: 20, better: 70, best: 10 })

  const handleNewEstimate = () => {
    setCurrentProject(null)
    setRooms([])
    setFloorPlanId(null)
    setPlanImageUrl(null)
    setSchematicData(null)
    setEstimateSummary(null)
    setProjectMode('estimate')
    setView('estimate')
  }

  const handleNewFloorPlan = () => {
    setCurrentProject(null)
    setRooms([])
    setFloorPlanId(null)
    setPlanImageUrl(null)
    setSchematicData(null)
    setTier('better')
    setProjectMode('floorplan')
    setView('upload')
  }

  const handleProjectSelect = async (project) => {
    setCurrentProject(project)
    setTier(project.tier || 'better')

    // Check if project has an estimate
    try {
      const res = await axios.get(`/api/projects/${project.id}/estimate`)
      setProjectMode('estimate')
      setRooms(res.data.rooms || [])
      setEstimateSummary(res.data.summary || null)
      setTierPcts({ good: res.data.pct_good, better: res.data.pct_better, best: res.data.pct_best })
      setView('results')
      return
    } catch (err) {
      // No estimate — check for floor plans
    }

    const plans = project.floor_plans || []
    if (plans.length > 0 && plans[0].rooms && plans[0].rooms.length > 0) {
      setProjectMode('floorplan')
      setFloorPlanId(plans[0].id)
      setRooms(plans[0].rooms)
      setSchematicData(plans[0].schematic_layout || null)
      const plan = plans[0]
      setPlanImageUrl(`/uploads/${project.id}/${plan.original_filename}`)
      setView('results')
    } else {
      setSchematicData(null)
      setView('upload')
    }
  }

  const handleEstimateComplete = (projectId, estimateRooms, summary) => {
    setCurrentProject(prev => prev || { id: projectId, name: 'Estimate' })
    setProjectMode('estimate')
    setRooms(estimateRooms)
    setEstimateSummary(summary)
    setView('results')
  }

  const handleUploadComplete = (data, projectData, imageUrl) => {
    setCurrentProject(projectData)
    setProjectMode('floorplan')
    setFloorPlanId(data.floor_plan_id)
    setRooms(data.rooms || [])
    setSchematicData(data.schematic_layout || null)
    setPlanImageUrl(imageUrl)
    setView('results')
  }

  const handleBackToList = () => {
    setView('list')
    setCurrentProject(null)
    setRooms([])
    setSchematicData(null)
    setEstimateSummary(null)
  }

  const handleTierChange = useCallback(async (newTier) => {
    setTier(newTier)
    if (!currentProject?.id || !floorPlanId) return

    setTierLoading(true)
    try {
      await axios.patch(`/api/projects/${currentProject.id}`, { tier: newTier })
      const res = await axios.post(
        `/api/projects/${currentProject.id}/plans/${floorPlanId}/parse`
      )
      setRooms(res.data.rooms || [])
      setSchematicData(res.data.schematic_layout || null)
      setCurrentProject(prev => ({ ...prev, tier: newTier }))
    } catch (err) {
      console.error('Failed to update tier:', err)
    } finally {
      setTierLoading(false)
    }
  }, [currentProject?.id, floorPlanId])

  // Build fixture schedule rooms from estimate data (adapt format)
  const scheduleRooms = projectMode === 'estimate'
    ? rooms.map(r => ({
        id: r.id,
        name: r.name,
        room_type: r.room_type,
        fixtures: (r.fixtures || []).map((f, i) => ({
          id: `${r.id}-${i}`,
          fixture_type: f.fixture_type,
          product_sku: f.product_sku,
          product_desc: f.product_desc,
          msrp_range: f.msrp_range,
          notes: f.notes,
          is_prewire: f.is_prewire,
        })),
      }))
    : rooms

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
            onNewProject={handleNewEstimate}
            onNewFloorPlan={handleNewFloorPlan}
            onSelectProject={handleProjectSelect}
          />
        )}

        {view === 'estimate' && (
          <EstimateBuilder
            existingProject={currentProject}
            onComplete={handleEstimateComplete}
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
                  {currentProject?.name || 'Estimate Results'}
                </h2>
                {currentProject?.address && (
                  <p className="text-gray-500 mt-1">{currentProject.address}</p>
                )}
              </div>
              {projectMode === 'floorplan' && (
                <div className="flex items-center gap-3">
                  {tierLoading && (
                    <div className="w-5 h-5 border-2 border-gold border-t-transparent rounded-full animate-spin" />
                  )}
                  <TierSelector value={tier} onChange={handleTierChange} />
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Left column */}
              <div>
                {projectMode === 'estimate' ? (
                  <EstimateSummaryCard
                    summary={estimateSummary}
                    rooms={rooms}
                    pctGood={tierPcts.good}
                    pctBetter={tierPcts.better}
                    pctBest={tierPcts.best}
                  />
                ) : (
                  <FloorPlanCanvas
                    rooms={rooms}
                    imageUrl={planImageUrl}
                  />
                )}
              </div>

              {/* Right: fixture schedule */}
              <div>
                <FixtureSchedule
                  rooms={scheduleRooms}
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
