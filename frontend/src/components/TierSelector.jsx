const TIERS = [
  { value: 'good', label: 'Good', desc: 'Builder Grade' },
  { value: 'better', label: 'Better', desc: 'DMF / WAC' },
  { value: 'best', label: 'Best', desc: 'Ketra' },
]

export default function TierSelector({ value, onChange }) {
  return (
    <div className="flex rounded-lg border border-gray-200 overflow-hidden">
      {TIERS.map(({ value: v, label, desc }) => (
        <button
          key={v}
          onClick={() => onChange(v)}
          className={`
            px-4 py-2 text-sm font-medium transition-all
            ${v === value
              ? 'bg-charcoal text-white'
              : 'bg-white text-gray-600 hover:bg-gray-50'
            }
            ${v !== 'good' ? 'border-l border-gray-200' : ''}
          `}
        >
          <div>{label}</div>
          <div className={`text-xs ${v === value ? 'text-gold' : 'text-gray-400'}`}>
            {desc}
          </div>
        </button>
      ))}
    </div>
  )
}
