import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'

/**
 * Рендер markdown-текста от LLM (отчёты по ценам, обоснования) с токенами дизайна.
 * Поддерживает GFM: таблицы, списки, заголовки, жирный/курсив, код, цитаты.
 */

const components: Components = {
  h1: ({ children }) => (
    <h1 style={{ fontSize: 18, fontWeight: 700, margin: '14px 0 6px', color: 'var(--text)' }}>{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 style={{ fontSize: 16, fontWeight: 700, margin: '14px 0 6px', color: 'var(--text)' }}>{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 style={{ fontSize: 14, fontWeight: 600, margin: '12px 0 4px', color: 'var(--text)' }}>{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 style={{ fontSize: 13, fontWeight: 600, margin: '10px 0 4px', color: 'var(--text-muted)' }}>{children}</h4>
  ),
  p: ({ children }) => (
    <p style={{ margin: '6px 0', lineHeight: 1.55 }}>{children}</p>
  ),
  ul: ({ children }) => (
    <ul style={{ margin: '6px 0', paddingLeft: 20, listStyle: 'disc', display: 'flex', flexDirection: 'column', gap: 2 }}>{children}</ul>
  ),
  ol: ({ children }) => (
    <ol style={{ margin: '6px 0', paddingLeft: 20, listStyle: 'decimal', display: 'flex', flexDirection: 'column', gap: 2 }}>{children}</ol>
  ),
  li: ({ children }) => <li style={{ lineHeight: 1.5 }}>{children}</li>,
  strong: ({ children }) => <strong style={{ fontWeight: 600, color: 'var(--text)' }}>{children}</strong>,
  em: ({ children }) => <em style={{ fontStyle: 'italic' }}>{children}</em>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)', textDecoration: 'underline' }}>{children}</a>
  ),
  hr: () => <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '12px 0' }} />,
  blockquote: ({ children }) => (
    <blockquote style={{ borderLeft: '3px solid var(--border-strong)', paddingLeft: 12, margin: '8px 0', color: 'var(--text-muted)' }}>{children}</blockquote>
  ),
  code: ({ className, children }) => {
    const isBlock = (className ?? '').includes('language-')
    if (isBlock) {
      return (
        <pre style={{ background: 'var(--bg-sunken)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: 12, overflowX: 'auto', margin: '8px 0', fontSize: 12.5 }}>
          <code>{children}</code>
        </pre>
      )
    }
    return (
      <code style={{ background: 'var(--bg-sunken)', borderRadius: 4, padding: '1px 5px', fontSize: '0.9em', fontFamily: 'var(--font-mono, ui-monospace, monospace)' }}>{children}</code>
    )
  },
  table: ({ children }) => (
    <div style={{ overflowX: 'auto', margin: '10px 0', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead style={{ background: 'var(--surface-2)' }}>{children}</thead>,
  th: ({ children, style }) => (
    <th style={{
      textAlign: (style?.textAlign as 'left' | 'right' | 'center') ?? 'left',
      padding: '7px 12px',
      fontWeight: 600,
      color: 'var(--text-muted)',
      borderBottom: '1px solid var(--border)',
      whiteSpace: 'nowrap',
      fontVariantNumeric: 'tabular-nums',
    }}>{children}</th>
  ),
  td: ({ children, style }) => (
    <td style={{
      textAlign: (style?.textAlign as 'left' | 'right' | 'center') ?? 'left',
      padding: '7px 12px',
      borderTop: '1px solid var(--border-faint)',
      fontVariantNumeric: 'tabular-nums',
    }}>{children}</td>
  ),
}

export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={className} style={{ fontSize: 14, color: 'var(--text)' }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  )
}
