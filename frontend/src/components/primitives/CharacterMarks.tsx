export function CharacterMarksRow() {
  const avatars = [
    {
      id: 'student-dev',
      label: 'Student Developer',
      borderColor: '#097fe8',
      svg: (
        <svg viewBox="0 0 40 40" width="32" height="32" fill="none" aria-hidden="true">
          <path d="M10 15c0-5 4-8 10-8s10 3 10 8v2H10v-2Z" fill="#111111" />
          <circle cx="20" cy="21" r="8" fill="#ffffff" stroke="#111111" strokeWidth="2" />
          <circle cx="17" cy="20" r="1.5" fill="#111111" />
          <circle cx="23" cy="20" r="1.5" fill="#111111" />
          <path d="M17 24.5c1.5 1.3 4.5 1.3 6 0" stroke="#111111" strokeWidth="1.8" strokeLinecap="round" />
          <rect x="13.5" y="18" width="5.5" height="4" rx="1" stroke="#097fe8" strokeWidth="1.5" />
          <rect x="21" y="18" width="5.5" height="4" rx="1" stroke="#097fe8" strokeWidth="1.5" />
          <line x1="19" y1="19.5" x2="21" y2="19.5" stroke="#097fe8" strokeWidth="1.5" />
        </svg>
      ),
    },
    {
      id: 'ast-mapper',
      label: 'Code Mapper Agent',
      borderColor: '#ffb110',
      svg: (
        <svg viewBox="0 0 40 40" width="32" height="32" fill="none" aria-hidden="true">
          <rect x="10" y="11" width="20" height="18" rx="5" fill="#ffffff" stroke="#111111" strokeWidth="2" />
          <line x1="20" y1="6" x2="20" y2="11" stroke="#111111" strokeWidth="2" strokeLinecap="round" />
          <circle cx="20" cy="5.5" r="2" fill="#ffb110" stroke="#111111" strokeWidth="1.5" />
          <circle cx="16" cy="19" r="1.8" fill="#111111" />
          <circle cx="24" cy="19" r="1.8" fill="#111111" />
          <path d="M16 24h8" stroke="#111111" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      ),
    },
    {
      id: 'educator-reviewer',
      label: 'Course Lecturer',
      borderColor: '#f64932',
      svg: (
        <svg viewBox="0 0 40 40" width="32" height="32" fill="none" aria-hidden="true">
          <path d="M20 8L8 13.5 20 19l12-5.5L20 8Z" fill="#111111" />
          <circle cx="20" cy="23" r="7.5" fill="#ffffff" stroke="#111111" strokeWidth="2" />
          <circle cx="17.5" cy="22" r="1.4" fill="#111111" />
          <circle cx="22.5" cy="22" r="1.4" fill="#111111" />
          <path d="M17.5 26c1.5 1 3.5 1 5 0" stroke="#f64932" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      ),
    },
    {
      id: 'viva-examiner',
      label: 'Viva Examiner',
      borderColor: '#62aef0',
      svg: (
        <svg viewBox="0 0 40 40" width="32" height="32" fill="none" aria-hidden="true">
          <circle cx="20" cy="20" r="9.5" fill="#ffffff" stroke="#111111" strokeWidth="2" />
          <path d="M13 15c2-3 12-3 14 0" stroke="#111111" strokeWidth="2" strokeLinecap="round" />
          <circle cx="16.8" cy="20" r="1.5" fill="#111111" />
          <circle cx="23.2" cy="20" r="1.5" fill="#111111" />
          <path d="M17 24.5c1.8 1.5 4.2 1.5 6 0" stroke="#0075de" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      ),
    },
    {
      id: 'chunk-indexer',
      label: 'Chunk Indexer',
      borderColor: '#097fe8',
      svg: (
        <svg viewBox="0 0 40 40" width="32" height="32" fill="none" aria-hidden="true">
          <rect x="9" y="10" width="22" height="20" rx="4" fill="#ffffff" stroke="#111111" strokeWidth="2" />
          <path d="M14 17l3 3-3 3" stroke="#f64932" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          <line x1="20" y1="23" x2="26" y2="23" stroke="#111111" strokeWidth="2" strokeLinecap="round" />
        </svg>
      ),
    },
    {
      id: 'debugger-guide',
      label: 'Trace & Debug Guide',
      borderColor: '#ffb110',
      svg: (
        <svg viewBox="0 0 40 40" width="32" height="32" fill="none" aria-hidden="true">
          <circle cx="19" cy="19" r="7.5" fill="#ffffff" stroke="#111111" strokeWidth="2" />
          <line x1="24.5" y1="24.5" x2="30" y2="30" stroke="#111111" strokeWidth="2.4" strokeLinecap="round" />
          <circle cx="17" cy="18.5" r="1.3" fill="#111111" />
          <circle cx="21" cy="18.5" r="1.3" fill="#111111" />
          <path d="M17 21.5c1 0.8 3 0.8 4 0" stroke="#111111" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      ),
    },
    {
      id: 'evidence-scribe',
      label: 'Evidence Scribe',
      borderColor: '#f64932',
      svg: (
        <svg viewBox="0 0 40 40" width="32" height="32" fill="none" aria-hidden="true">
          <path
            d="M12 10h12l5 5v15a2 2 0 0 1-2 2H12a2 2 0 0 1-2-2V12a2 2 0 0 1 2-2Z"
            fill="#ffffff"
            stroke="#111111"
            strokeWidth="2"
          />
          <path d="M15 21l3 3 6-6" stroke="#0075de" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ),
    },
  ]

  return (
    <div className="notion-character-cluster" aria-hidden="true">
      <svg className="notion-doodle notion-doodle--left" width="36" height="36" viewBox="0 0 36 36" fill="none">
        <path
          d="M18 4l2.8 8.7L29.5 15.5l-8.7 2.8L18 27l-2.8-8.7L6.5 15.5l8.7-2.8L18 4Z"
          stroke="#ffb110"
          strokeWidth="2"
          fill="#ffffff"
          strokeLinejoin="round"
        />
      </svg>

      <div className="notion-avatar-row">
        {avatars.map((avatar, index) => (
          <div
            key={avatar.id}
            className="notion-avatar-mark"
            style={{
              borderColor: avatar.borderColor,
              animationDelay: `${index * 60}ms`,
            }}
            title={avatar.label}
          >
            {avatar.svg}
          </div>
        ))}
      </div>

      <svg className="notion-doodle notion-doodle--right" width="44" height="32" viewBox="0 0 44 32" fill="none">
        <path
          d="M4 24c7-14 14 4 22-10 4-7 10-6 14-2"
          stroke="#f64932"
          strokeWidth="2.2"
          strokeLinecap="round"
        />
        <circle cx="39" cy="12" r="2.5" fill="#097fe8" />
      </svg>
    </div>
  )
}
