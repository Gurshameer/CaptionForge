import { useState, useEffect } from 'react';

export default function Header() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => {
      if (window.scrollY > 24) setScrolled(true);
      else setScrolled(false);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header className={scrolled ? 'scrolled' : ''}>
      <nav className="nav wrap">
        {/* Brand — left side */}
        <div className="brand">
          {/* CaptionForge logo: three overlapping circles */}
          <svg className="brand-logo-svg" viewBox="0 0 64 36" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="14" cy="18" r="13" stroke="#1C1410" strokeWidth="2.5" fill="none"/>
            <circle cx="32" cy="18" r="13" stroke="#1C1410" strokeWidth="2.5" fill="none"/>
            <circle cx="50" cy="18" r="13" stroke="#1C1410" strokeWidth="2.5" fill="none"/>
            {/* Overlapping lens shapes */}
            <path d="M25 18 C25 12 32 8 32 8 C32 8 39 12 39 18 C39 24 32 28 32 28 C32 28 25 24 25 18Z" fill="#1C1410"/>
            {/* Orange accent on right circle */}
            <path d="M43 10 C46 11 50 14 50 18 C50 22 46 25 43 26 C45 23 46 20.5 46 18 C46 15.5 45 13 43 10Z" fill="#BD462A"/>
            {/* Small dot in left circle */}
            <circle cx="10" cy="15" r="2" fill="#1C1410"/>
          </svg>
          <span className="brand-name">CaptionForge</span>
        </div>

        {/* Right side tag */}
        <span className="nav-tag">Subtitle &amp; Voice Studio</span>
      </nav>
    </header>
  );
}
