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
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const handleFileSelect = (e) => {
    const file = e.target.files[0]
    if (file) handleFile(file)
  }

  const handleFile = async (file) => {
    // Validate file type
    const validTypes = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg']
    if (!validTypes.includes(file.type)) {
      setError('Please upload a PDF, PNG or JPG file.')
      return
    }

    // Validate file size (50MB max)
    if (file.size > 50 * 1024 * 1024) {
      setError('File is too large. Maximum size is 50MB.')
      return
    }

    if (!projectName.trim()) {
      setError('Please enter a project name before uploading.')
      return
    }

    setError(null)
    setUploading(true)
    setStep(0)

    try {
      // Step 1: Create project (or use existing)
      let project = existingProject
      if (!project) {
        const createRes = await axios.post('/api/projects', {
          name: projectName.trim(),
          address: projectAddress.trim(),
          tier,
        })
        project = createRes.data
      }

      // Step 2: Upload file
      setStep(1)
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

      // Step 3: Done
      setStep(3)

      // Build the image URL for display
      const imageUrl = file.type.startsWith('image/')
        ? URL.createObjectURL(file)
        : null

      onComplete(uploadRes.data, project, imageUrl)
    } catch (err) {
      console.error('Upload failed:', err)
      const detail = err.response?.data?.detail || err.message || 'Upload failed. Please try again.'
      setError(detail)
      setUploading(false)
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
              Project Name *
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
              {dragging ? 'Drop your floor plan here' : 'Upload a floor plan'}
            </p>
            <p className="text-sm text-gray-500 mt-1">
              Drag and drop or click to browse. Accepts PDF, PNG and JPG.
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
