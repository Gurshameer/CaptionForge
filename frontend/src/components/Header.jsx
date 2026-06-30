import { useState, useEffect } from 'react';
import logo from '../assets/logo.png';
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
          <img src={logo} alt="CaptionForge Logo" className="brand-logo-img" />
          <span className="brand-name">CaptionForge</span>
        </div>

        {/* Right side tag */}
        <span className="nav-tag">Subtitle &amp; Voice Studio</span>
      </nav>
    </header>
  );
}
