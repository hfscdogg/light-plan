/**
 * Floor plan viewer with fixture overlay.
 *
 * Phase 1: Displays the uploaded plan image as a reference.
 * Phase 2: Interactive canvas with drag-drop fixture placement.
 */

export default function FloorPlanCanvas({ imageUrl }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div className="bg-charcoal-light px-4 py-2">
        <h3 className="text-white text-sm font-medium">Floor Plan</h3>
      </div>

      <div className="p-4">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt="Uploaded floor plan"
            className="w-full h-auto rounded border border-gray-200"
          />
        ) : (
          <div className="aspect-[4/3] bg-gray-100 rounded flex items-center justify-center">
            <div className="text-center text-gray-400">
              <svg className="w-12 h-12 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <p className="text-sm">Plan image preview</p>
              <p className="text-xs mt-1">Interactive overlay coming in Phase 2</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
