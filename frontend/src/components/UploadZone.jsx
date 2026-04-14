import { useState, useRef } from 'react'
import axios from 'axios'

const STEPS = [
  'Uploading floor plan...',
  'Analyzing rooms with AI...',
  'Assigning fixtures...',
  'Done!',
]

export default function UploadZone({ tier, existingProject, onComplete }) {
  const [projectName, setProjectName] = useState(existingProject?.name || '')
  const [projectAddress, setProjectAddress] = useState(existingProject?.address || '')
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [step, setStep] = useState(0)
  const [progressLabel, setProgressLabel] = useState('')
  const [error, setError] = useState(null)
  const fileInputRef = useRef(null)

  const handleDragOver = (e) => {
    e.preventDefault()
    setDragging(true)
  }

  const handleDragLeave = () => {
    setDragging(false)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const files = Array.from(e.dataTransfer.files || [])
    if (files.length > 0) handleFiles(files)
  }

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files || [])
    if (files.length > 0) handleFiles(files)
  }

  const handleFiles = async (files) => {
    // Validate each file type + size
    const validTypes = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg']
    for (const file of files) {
      if (!validTypes.includes(file.type)) {
        setError(`"${file.name}" is not a PDF, PNG or JPG file.`)
        return
      }
      if (file.size > 50 * 1024 * 1024) {
        setError(`"${file.name}" is too large. Maximum size is 50MB.`)
        return
      }
    }

    setError(null)
    setUploading(true)
    setStep(0)
    setProgressLabel(files.length > 1 ? `File 1 of ${files.length}` : '')

    try {
      // Step 1: Create project (or use existing). Name + address are optional —
      // we fall back to a default so uploads aren't blocked.
      let project = existingProject
      if (!project) {
        const createRes = await axios.post('/api/projects', {
          name: projectName.trim() || 'Untitled Project',
          address: projectAddress.trim() || null,
          tier,
        })
        project = createRes.data
      }

      // Upload each file sequentially, accumulating rooms from every plan so
      // the fixture schedule shows them all together.
      const allRooms = []
      let lastUploadData = null
      let firstImageUrl = null

      for (let i = 0; i < files.length; i++) {
        const file = files[i]
        setStep(1)
        setProgressLabel(files.length > 1 ? `File ${i + 1} of ${files.length}` : '')

        const formData = new FormData()
        formData.append('file', file)

        setStep(2)
        const uploadRes = await axios.post(
          `/api/projects/${project.id}/plans/upload`,
          formData,
          {
            headers: { 'Content-Type': 'multipart/form-data' },
            timeout: 120000, // 2 min timeout for AI analysis
          }
        )

        lastUploadData = uploadRes.data
        if (uploadRes.data?.rooms) {
          allRooms.push(...uploadRes.data.rooms)
        }

        if (firstImageUrl == null && file.type.startsWith('image/')) {
          firstImageUrl = URL.createObjectURL(file)
        }
      }

      setStep(3)

      // Pass combined rooms back to the parent. floor_plan_id is the last
      // plan we uploaded — callers only use it for reparse + export.
      onComplete(
        { ...(lastUploadData || {}), rooms: allRooms },
        project,
        firstImageUrl,
      )
    } catch (err) {
      console.error('Upload failed:', err)
      const detail = err.response?.data?.detail || err.message || 'Upload failed. Please try again.'
      setError(detail)
      setUploading(false)
      setProgressLabel('')
    }
  }

  if (uploading) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
        <div className="space-y-6">
          {/* Progress indicator */}
          <div className="flex justify-center">
            <div className="w-12 h-12 border-4 border-gold border-t-transparent rounded-full animate-spin" />
          </div>

          {progressLabel && (
            <div className="text-sm text-gray-500">{progressLabel}</div>
          )}

          {/* Step messages */}
          <div className="space-y-2">
            {STEPS.map((label, i) => (
              <div
                key={i}
                className={`text-sm transition-all duration-300 ${
                  i < step
                    ? 'text-green-600'
                    : i === step
                    ? 'text-charcoal font-medium'
                    : 'text-gray-300'
                }`}
              >
                {i < step ? '\u2713 ' : i === step ? '\u25CB ' : '\u25CB '}
                {label}
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Project details form */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="project-name" className="block text-sm font-medium text-gray-700 mb-1">
              Project Name
            </label>
            <input
              id="project-name"
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="Smith Residence"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold focus:border-gold"
            />
          </div>
          <div>
            <label htmlFor="project-address" className="block text-sm font-medium text-gray-700 mb-1">
              Address / Lot
            </label>
            <input
              id="project-address"
              type="text"
              value={projectAddress}
              onChange={(e) => setProjectAddress(e.target.value)}
              placeholder="123 Oak Lane, Lot 4"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold focus:border-gold"
            />
          </div>
        </div>
        <p className="text-xs text-gray-500 mt-3">
          Both fields are optional. You can upload a plan right away and fill these in later.
        </p>
      </div>

      {/* Upload zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`
          bg-white rounded-lg border-2 border-dashed p-16 text-center cursor-pointer
          transition-all duration-200
          ${dragging
            ? 'border-gold bg-gold/5 scale-[1.01]'
            : 'border-gray-300 hover:border-gold hover:bg-gray-50'
          }
        `}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          multiple
          onChange={handleFileSelect}
          className="hidden"
        />

        <div className="space-y-4">
          {/* Upload icon */}
          <svg
            className={`w-16 h-16 mx-auto transition-colors ${
              dragging ? 'text-gold' : 'text-gray-400'
            }`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
            />
          </svg>

          <div>
            <p className="text-lg font-medium text-charcoal">
              {dragging ? 'Drop your floor plans here' : 'Upload floor plans'}
            </p>
            <p className="text-sm text-gray-500 mt-1">
              Drag and drop or click to browse. Select one or more PDF, PNG or JPG files.
            </p>
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm">
          {error}
        </div>
      )}
    </div>
  )
}
