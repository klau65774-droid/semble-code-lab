import type { ReactNode } from 'react';
import { Icon } from './ui';

const keywords = new Set([
  'async', 'await', 'break', 'case', 'catch', 'class', 'const', 'continue', 'def', 'default',
  'delete', 'elif', 'else', 'enum', 'except', 'export', 'extends', 'false', 'finally', 'for',
  'from', 'function', 'if', 'implements', 'import', 'in', 'interface', 'is', 'lambda', 'let',
  'new', 'None', 'not', 'null', 'or', 'pass', 'private', 'public', 'raise', 'return', 'self',
  'static', 'this', 'True', 'try', 'type', 'typeof', 'undefined', 'var', 'while', 'with', 'yield',
]);

function highlightLine(line: string): ReactNode[] {
  const tokens = line.split(/(\[[^\]\n]*REDACTED[^\]\n]*\]|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|#.*$|\/\/.*$|\b[A-Za-z_][A-Za-z0-9_]*\b|\b\d+(?:\.\d+)?\b)/gi);
  return tokens.filter((token) => token !== '').map((token, index) => {
    let className = '';
    if (/REDACTED/i.test(token)) className = 'code-token--redacted';
    else if (token.startsWith('#') || token.startsWith('//')) className = 'code-token--comment';
    else if (/^["']/.test(token)) className = 'code-token--string';
    else if (keywords.has(token)) className = 'code-token--keyword';
    else if (/^\d/.test(token)) className = 'code-token--number';
    else if (/^[A-Z][A-Za-z0-9_]*$/.test(token)) className = 'code-token--type';
    return className ? <span className={className} key={index}>{token}</span> : <span key={index}>{token}</span>;
  });
}

export function CodeBlock({
  content,
  startLine,
  secretsRedacted = 0,
  maxHeight = 220,
}: {
  content: string;
  startLine: number;
  secretsRedacted?: number;
  maxHeight?: number;
}) {
  return (
    <div className="code-block">
      {secretsRedacted > 0 && (
        <div className="redaction-note">
          <Icon name="lock" size={11} />
          {secretsRedacted} credential{secretsRedacted === 1 ? '' : 's'} replaced with REDACTED
        </div>
      )}
      <div className="code-block__scroller" style={{ maxHeight }}>
        {content.split('\n').map((line, index) => (
          <div className="code-line" key={`${startLine + index}-${line}`}>
            <span className="code-line__number">{startLine + index}</span>
            <code>{highlightLine(line)}</code>
          </div>
        ))}
      </div>
    </div>
  );
}
