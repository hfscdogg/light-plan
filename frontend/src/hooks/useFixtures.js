import { useState, useCallback, useMemo } from 'react'
import axios from 'axios'
import { estimateRoomFixtures, estimateTotalFixtures } from '../utils/lightingRules'

/**
 * Hook for managing fixture data and tier changes.
 */
export default function useFixtures(rooms, tier = 'better') {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  /**
   * Client-side fixture estimates for instant tier preview.
   * These are approximate and used only for the UI.
   * The server data (in rooms[].fixtures) is authoritative.
   */
  const estimates = useMemo(() => {
    return rooms.map((room) => ({
      roomName: room.name,
      roomType: room.room_type,
      fixtures: estimateRoomFixtures(room, tier),
    }))
  }, [rooms, tier])

  const totalEstimate = useMemo(() => {
    return estimateTotalFixtures(rooms, tier)
  }, [rooms, tier])

  /**
   * Re-assign fixtures on the server for a new tier.
   * This updates the project tier and re-runs the lighting engine.
   */
  const reassignForTier = useCallback(async (projectId, planId, newTier) => {
    setLoading(true)
    setError(null)

    try {
      // Update the project tier
      await axios.patch(`/api/projects/${projectId}`, { tier: newTier })

      // Re-parse to re-run the lighting engine with the new tier
      const res = await axios.post(
        `/api/projects/${projectId}/plans/${planId}/parse`
      )

      return res.data
    } catch (err) {
      const detail = err.response?.data?.detail || err.message
      setError(detail)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const exportPdf = useCallback(async (projectId) => {
    try {
      const res = await axios.get(`/api/exports/projects/${projectId}/pdf`, {
        responseType: 'blob',
      })

      const url = URL.createObjectURL(
        new Blob([res.data], { type: 'application/pdf' })
      )
      const a = document.createElement('a')
      a.href = url
      a.download = `LightPlan_${projectId}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('PDF export failed:', err)
      throw err
    }
  }, [])

  return {
    estimates,
    totalEstimate,
    loading,
    error,
    reassignForTier,
    exportPdf,
  }
}
