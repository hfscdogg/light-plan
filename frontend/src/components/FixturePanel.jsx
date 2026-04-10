/**
 * Fixture palette and properties sidebar.
 *
 * Phase 1: Placeholder showing what will be available.
 * Phase 2: Drag-drop fixture palette, property editing, zone assignment.
 */

export default function FixturePanel() {
  return (
    <div className="bg-white rounded-lg border border-gray-200 mt-4 overflow-hidden">
      <div className="bg-charcoal-light px-4 py-2">
        <h3 className="text-white text-sm font-medium">Fixture Palette</h3>
      </div>
      <div className="p-4 text-center text-gray-400 text-sm">
        <p>Drag-and-drop fixture editing</p>
        <p className="text-xs mt-1">Coming in Phase 2</p>
      </div>
    </div>
  )
}
