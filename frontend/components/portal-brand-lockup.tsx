type PortalBrandLockupProps = {
  title?: string;
  subtitle?: string;
  eyebrow?: string;
  logoAlt?: string;
  tone?: "light" | "dark";
  compact?: boolean;
  className?: string;
};

export default function PortalBrandLockup({
  title = "Piano Academie",
  subtitle,
  eyebrow,
  logoAlt = "Logo Piano Academie",
  tone = "dark",
  compact = false,
  className = "",
}: PortalBrandLockupProps): JSX.Element {
  const classes = ["portal-brand-lockup", `tone-${tone}`, compact ? "is-compact" : "", className].filter(Boolean).join(" ");
  return (
    <div className={classes}>
      <img
        className="portal-brand-lockup-logo"
        src="/brand/logo-piano-academie.png"
        alt={logoAlt}
      />
      <div className="portal-brand-lockup-copy">
        {eyebrow ? <span className="portal-brand-lockup-eyebrow">{eyebrow}</span> : null}
        <strong>{title}</strong>
        {subtitle ? <small>{subtitle}</small> : null}
      </div>
    </div>
  );
}
