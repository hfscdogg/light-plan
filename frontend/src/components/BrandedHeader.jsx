export default function BrandedHeader({ onLogoClick, showBack, onBack }) {
  return (
    <header className="bg-charcoal text-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center gap-4">
            {showBack && (
              <button
                onClick={onBack}
                className="text-gray-400 hover:text-white transition-colors"
                aria-label="Back to projects"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
            )}
            <button
              onClick={onLogoClick}
              className="flex items-center gap-3 hover:opacity-90 transition-opacity"
            >
              {/* Lightbulb icon */}
              <svg className="w-8 h-8 text-gold" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2a7 7 0 00-7 7c0 2.38 1.19 4.47 3 5.74V17a1 1 0 001 1h6a1 1 0 001-1v-2.26c1.81-1.27 3-3.36 3-5.74a7 7 0 00-7-7zm2 14h-4v-1h4v1zm-1-3h-2v-2.59l-1.3-1.29 1.42-1.42L12 9.59l.88-.88 1.42 1.42L13 11.41V13z"/>
                <path d="M10 20h4v1a1 1 0 01-1 1h-2a1 1 0 01-1-1v-1z"/>
              </svg>
              <div>
                <span className="text-lg font-bold tracking-wider">LIGHTPLAN</span>
                <span className="text-gold text-xs ml-2 font-medium">by Livewire</span>
              </div>
            </button>
          </div>
        </div>
      </div>
    </header>
  )
}
