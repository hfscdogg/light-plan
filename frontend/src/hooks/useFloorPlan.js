import { useState, useCallback } from 'react'
import axios from 'axios'

/**
 * Hook for managing floor plan parsing state and API calls.
 */
export default function useFloorPlan() {
  const [rooms, setRooms] = useState([])
  const [floorPlanId, setFloorPlanId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const uploadPlan = useCallback(async (projectId, file) => {
    setLoading(true)
    setError(null)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const res = await axios.post(
        `/api/projects/${projectId}/plans/upload`,
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 120000,
        }
      )

      setFloorPlanId(res.data.floor_plan_id)
      setRooms(res.data.rooms || [])
      return res.data
    } catch (err) {
      const detail = err.response?.data?.detail || err.message
      setError(detail)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const reparsePlan = useCallback(async (projectId, planId) => {
    setLoading(true)
    setError(null)

    try {
      const res = await axios.post(
        `/api/projects/${projectId}/plans/${planId}/parse`
      )

      setRooms(res.data.rooms || [])
      return res.data
    } catch (err) {
      const detail = err.response?.data?.detail || err.message
      setError(detail)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const loadPlan = useCallback(async (projectId, planId) => {
    setLoading(true)
    setError(null)

    try {
      const res = await axios.get(
        `/api/projects/${projectId}/plans/${planId}`
      )

      setFloorPlanId(res.data.id)
      setRooms(res.data.rooms || [])
      return res.data
    } catch (err) {
      const detail = err.response?.data?.detail || err.message
      setError(detail)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const reset = useCallback(() => {
    setRooms([])
    setFloorPlanId(null)
    setError(null)
  }, [])

  return {
    rooms,
    floorPlanId,
    loading,
    error,
    uploadPlan,
    reparsePlan,
    loadPlan,
    reset,
  }
}
