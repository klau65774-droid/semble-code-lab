import type { ReactNode } from 'react';

export function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ');
}

export type IconName =
  | 'activity'
  | 'alert'
  | 'branch'
  | 'check'
  | 'chevron-down'
  | 'code'
  | 'cpu'
  | 'database'
  | 'file'
  | 'folder'
  | 'layers'
  | 'lock'
  | 'play'
  | 'refresh'
  | 'search'
  | 'shield'
  | 'sliders'
  | 'zap';

export function Icon({ name, size = 16, className }: { name: IconName; size?: number; className?: string }) {
  const paths: Record<IconName, ReactNode> = {
    activity: <path d="M3 12h4l2.5-7 5 14 2.5-7h4" />,
    alert: <><path d="M12 3 2.8 20h18.4L12 3Z" /><path d="M12 9v4m0 3.5v.1" /></>,
    branch: <><circle cx="6" cy="5" r="2" /><circle cx="18" cy="6" r="2" /><circle cx="6" cy="19" r="2" /><path d="M6 7v10m2-9c5 0 3-2 8-2" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    'chevron-down': <path d="m6 9 6 6 6-6" />,
    code: <><path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-14-2 16" /></>,
    cpu: <><rect x="6" y="6" width="12" height="12" rx="2" /><path d="M9 1v3m6-3v3M9 20v3m6-3v3M1 9h3m-3 6h3m16-6h3m-3 6h3M10 10h4v4h-4z" /></>,
    database: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7" /></>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 13h8m-8 4h5" /></>,
    folder: <path d="M3 6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />,
    layers: <><path d="m12 2 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5M3 17l9 5 9-5" /></>,
    lock: <><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3" /></>,
    play: <path d="m8 5 11 7-11 7V5Z" />,
    refresh: <><path d="M20 7v5h-5" /><path d="M18.5 16a8 8 0 1 1 1.3-9L20 12" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
    shield: <><path d="M12 2 4 5v6c0 5 3.4 9.3 8 11 4.6-1.7 8-6 8-11V5l-8-3Z" /><path d="m9 12 2 2 4-5" /></>,
    sliders: <><path d="M4 6h16M4 12h16M4 18h16" /><circle cx="8" cy="6" r="2" /><circle cx="15" cy="12" r="2" /><circle cx="10" cy="18" r="2" /></>,
    zap: <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z" />,
  };

  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.7"
    >
      {paths[name]}
    </svg>
  );
}

export function Panel({
  title,
  action,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cx('panel', className)}>
      {(title || action) && (
        <header className="panel__header">
          {typeof title === 'string' ? <h2 className="panel__title">{title}</h2> : title}
          {action}
        </header>
      )}
      <div className={cx('panel__body', bodyClassName)}>{children}</div>
    </section>
  );
}

export type BadgeTone = 'neutral' | 'blue' | 'purple' | 'amber' | 'cyan' | 'emerald' | 'rose';

export function Badge({ children, tone = 'neutral', className }: { children: ReactNode; tone?: BadgeTone; className?: string }) {
  return <span className={cx('badge', `badge--${tone}`, className)}>{children}</span>;
}

export function Toggle({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      aria-checked={checked}
      aria-label={label}
      className={cx('toggle', checked && 'toggle--on')}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      role="switch"
      type="button"
    >
      <span className="toggle__thumb" />
    </button>
  );
}

export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="empty-state">
      <Icon name="code" size={20} />
      <p>{title}</p>
      {detail && <span>{detail}</span>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-state" role="alert">
      <Icon name="alert" size={16} />
      <span>{message}</span>
      {onRetry && <button type="button" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function LoadingState({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="loading-state" role="status">
      <span className="loading-state__dot" />
      {label}
    </div>
  );
}
