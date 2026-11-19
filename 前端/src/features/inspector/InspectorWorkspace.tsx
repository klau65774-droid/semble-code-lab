import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { FileChunks, FileSummary, RepoSummary } from '../../api/types';
import { CodeBlock } from '../../components/CodeBlock';
import { Badge, cx, EmptyState, ErrorState, Icon, LoadingState, Panel, Toggle } from '../../components/ui';
import { baseName, errorMessage, formatNumber } from '../../lib/format';

interface TreeNode {
  directories: Map<string, TreeNode>;
  files: FileSummary[];
}

function newNode(): TreeNode {
  return { directories: new Map(), files: [] };
}

function buildFileTree(files: FileSummary[]): TreeNode {
  const root = newNode();
  for (const file of files) {
    const parts = file.file_path.split(/[\\/]/).filter(Boolean);
    parts.pop();
    let node = root;
    for (const part of parts) {
      if (!node.directories.has(part)) node.directories.set(part, newNode());
      node = node.directories.get(part)!;
    }
    node.files.push(file);
  }
  return root;
}

function FileTreeBranch({
  node,
  depth,
  selectedPath,
  collapsed,
  onToggleDirectory,
  onSelectFile,
}: {
  node: TreeNode;
  depth: number;
  selectedPath: string;
  collapsed: Set<string>;
  onToggleDirectory: (path: string) => void;
  onSelectFile: (filePath: string) => void;
}) {
  const directoryEntries = [...node.directories.entries()].sort(([a], [b]) => a.localeCompare(b));
  const sortedFiles = [...node.files].sort((a, b) => a.file_path.localeCompare(b.file_path));

  return (
    <>
      {directoryEntries.map(([name, child]) => {
        const pathKey = `${depth}:${name}`;
        const isCollapsed = collapsed.has(pathKey);
        return (
          <div key={pathKey}>
            <button
              aria-expanded={!isCollapsed}
              className="tree-directory"
              onClick={() => onToggleDirectory(pathKey)}
              style={{ paddingLeft: `${8 + depth * 12}px` }}
              type="button"
            >
              <Icon name="chevron-down" size={11} className={cx(isCollapsed && '-rotate-90')} />
              <Icon name="folder" size={13} />
              <span>{name}</span>
            </button>
            {!isCollapsed && (
              <FileTreeBranch
                collapsed={collapsed}
                depth={depth + 1}
                node={child}
                onSelectFile={onSelectFile}
                onToggleDirectory={onToggleDirectory}
                selectedPath={selectedPath}
              />
            )}
          </div>
        );
      })}
      {sortedFiles.map((file) => {
        const isTest = /test|spec/i.test(file.file_path);
        const penaltyLabel = file.path_penalty < 1
          ? `${file.path_penalty.toFixed(2)}x ${isTest ? 'Test' : 'Path'} Penalty`
          : null;
        return (
          <button
            aria-label={`${file.file_path} ${file.language ?? 'text'} ${file.chunk_count} chunks ${file.estimated_tokens} tokens${penaltyLabel ? ` ${penaltyLabel}` : ''}${file.secrets_detected ? ` ${file.secrets_detected} secrets` : ''}`}
            className={cx('tree-file', selectedPath === file.file_path && 'tree-file--selected')}
            key={file.file_path}
            onClick={() => onSelectFile(file.file_path)}
            style={{ paddingLeft: `${8 + depth * 12}px` }}
            type="button"
          >
            <span className="tree-file__top">
              <Icon name="file" size={13} />
              <strong title={file.file_path}>{baseName(file.file_path)}</strong>
              {file.secrets_detected > 0 && (
                <span className="tree-file__secret"><Icon name="lock" size={11} />{file.secrets_detected} secrets</span>
              )}
            </span>
            <span className="tree-file__meta">
              <span>{file.language ?? 'text'}</span>
              <span>{file.chunk_count} chunks</span>
              <span>{formatNumber(file.estimated_tokens)} tok</span>
              <span>{formatNumber(file.total_lines)} lines</span>
            </span>
            {penaltyLabel && <Badge className="tree-file__penalty" tone="rose">{penaltyLabel}</Badge>}
          </button>
        );
      })}
    </>
  );
}

export function InspectorWorkspace({
  repo,
  onRepoIndexed,
}: {
  repo: RepoSummary | null;
  onRepoIndexed: (repo: RepoSummary) => void;
}) {
  const [path, setPath] = useState(repo?.path ?? '');
  const [repoId, setRepoId] = useState('');
  const [forceRebuild, setForceRebuild] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [indexError, setIndexError] = useState<string | null>(null);
  const [indexSuccess, setIndexSuccess] = useState<string | null>(null);
  const [files, setFiles] = useState<FileSummary[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [filesError, setFilesError] = useState<string | null>(null);
  const [selectedPath, setSelectedPath] = useState('');
  const [fileChunks, setFileChunks] = useState<FileChunks | null>(null);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [chunksError, setChunksError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const filesRequestRef = useRef(0);
  const chunksRequestRef = useRef(0);

  useEffect(() => {
    setPath(repo?.path ?? '');
  }, [repo?.path]);

  useEffect(() => {
    const requestId = ++filesRequestRef.current;
    setFiles([]);
    setSelectedPath('');
    setFileChunks(null);
    setFilesError(null);
    if (!repo) return;
    setFilesLoading(true);
    api.files(repo.repo_id)
      .then((data) => {
        if (requestId !== filesRequestRef.current) return;
        setFiles(data);
        setSelectedPath(data[0]?.file_path ?? '');
      })
      .catch((error: unknown) => {
        if (requestId === filesRequestRef.current) setFilesError(errorMessage(error));
      })
      .finally(() => {
        if (requestId === filesRequestRef.current) setFilesLoading(false);
      });
  }, [repo]);

  useEffect(() => {
    const requestId = ++chunksRequestRef.current;
    setFileChunks(null);
    setChunksError(null);
    if (!repo || !selectedPath) return;
    setChunksLoading(true);
    api.chunks(repo.repo_id, selectedPath)
      .then((data) => {
        if (requestId === chunksRequestRef.current) setFileChunks(data);
      })
      .catch((error: unknown) => {
        if (requestId === chunksRequestRef.current) setChunksError(errorMessage(error));
      })
      .finally(() => {
        if (requestId === chunksRequestRef.current) setChunksLoading(false);
      });
  }, [repo?.repo_id, selectedPath]);

  const tree = useMemo(() => buildFileTree(files), [files]);

  async function submitIndex(event: React.FormEvent) {
    event.preventDefault();
    const trimmedPath = path.trim();
    const trimmedRepoId = repoId.trim();
    if (!trimmedPath) {
      setIndexError('Local repository path is required.');
      return;
    }
    if (trimmedPath.length > 4096) {
      setIndexError('Local repository path must be 4,096 characters or fewer.');
      return;
    }
    if (trimmedRepoId && !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(trimmedRepoId)) {
      setIndexError('Repository ID must match ^[A-Za-z0-9][A-Za-z0-9_-]*$ and be at most 64 characters.');
      return;
    }

    setIndexing(true);
    setIndexError(null);
    setIndexSuccess(null);
    try {
      const indexed = await api.indexRepo({
        path: trimmedPath,
        ...(trimmedRepoId ? { repo_id: trimmedRepoId } : {}),
        force_rebuild: forceRebuild,
      });
      setIndexSuccess(`Indexed ${indexed.indexed_files} files · ${indexed.total_chunks} AST chunks in ${(indexed.index_ms / 1000).toFixed(2)}s`);
      onRepoIndexed(indexed);
    } catch (error) {
      setIndexError(errorMessage(error));
    } finally {
      setIndexing(false);
    }
  }

  return (
    <div className="inspector-page workspace-page">
      <section className="workspace-intro">
        <div>
          <span className="workspace-intro__eyebrow"><Icon name="code" size={14} /> TREE-SITTER STRUCTURE</span>
          <h1>AST Inspector</h1>
          <p>Inspect syntax-aware chunk boundaries, lexical terms, token estimates, and retrieval path penalties.</p>
        </div>
        {repo && (
          <div className="repo-stat-strip">
            <Badge tone="blue">{repo.name}</Badge>
            <span>{repo.indexed_files} files</span>
            <span>{repo.total_chunks} chunks</span>
            <span>{Object.keys(repo.languages).length} languages</span>
          </div>
        )}
      </section>

      <Panel className="index-panel">
        <form className="index-form" onSubmit={submitIndex}>
          <div className="index-form__path">
            <label htmlFor="repository-path">Local repository path</label>
            <input
              aria-label="Local repository path"
              className="text-input"
              id="repository-path"
              maxLength={4096}
              onChange={(event) => setPath(event.target.value)}
              placeholder="D:/workspace/your-repository"
              value={path}
            />
          </div>
          <div className="index-form__id">
            <label htmlFor="repository-id">Repository ID <span>(optional)</span></label>
            <input
              aria-label="Repository ID (optional)"
              className="text-input"
              id="repository-id"
              maxLength={64}
              onChange={(event) => setRepoId(event.target.value)}
              placeholder={repo?.repo_id ?? 'my-repository'}
              value={repoId}
            />
          </div>
          <div className="index-form__actions">
            <label className="force-control">
              <span>Force rebuild</span>
              <Toggle checked={forceRebuild} label="Force rebuild" onChange={setForceRebuild} />
            </label>
            <button className="primary-button" disabled={indexing} type="submit">
              <Icon name={indexing ? 'activity' : 'database'} size={14} />
              {indexing ? 'Indexing…' : 'Index Repository'}
            </button>
          </div>
        </form>
        {(indexError || indexSuccess) && (
          <div className="index-form__message">
            {indexError ? <ErrorState message={indexError} /> : <div className="index-success" role="status"><Icon name="check" size={14} />{indexSuccess}</div>}
          </div>
        )}
      </Panel>

      {!repo ? (
        <Panel><EmptyState title="No indexed snapshot" detail="Enter an allowed local repository path above to build the first AST index." /></Panel>
      ) : (
        <div className="inspector-grid">
          <Panel
            title="INDEXED FILES"
            className="files-panel"
            action={<Badge>{files.length} FILES</Badge>}
          >
            {filesLoading ? (
              <LoadingState label="Loading repository files" />
            ) : filesError ? (
              <ErrorState message={filesError} />
            ) : files.length === 0 ? (
              <EmptyState title="No indexed files" detail="This snapshot contains no files matching the indexed content types." />
            ) : (
              <div className="file-tree">
                <FileTreeBranch
                  collapsed={collapsed}
                  depth={0}
                  node={tree}
                  onSelectFile={setSelectedPath}
                  onToggleDirectory={(pathKey) => setCollapsed((current) => {
                    const next = new Set(current);
                    if (next.has(pathKey)) next.delete(pathKey);
                    else next.add(pathKey);
                    return next;
                  })}
                  selectedPath={selectedPath}
                />
              </div>
            )}
          </Panel>

          <Panel
            title="AST CHUNK ANATOMY"
            className="chunks-panel"
            action={fileChunks && <Badge tone="cyan">{fileChunks.chunks.length} SYNTAX NODES</Badge>}
          >
            {selectedPath && (
              <div className="chunk-source">
                <div><Icon name="file" size={13} /><span>{selectedPath}</span></div>
                {fileChunks && <span>{formatNumber(fileChunks.total_lines)} total lines</span>}
              </div>
            )}
            {chunksLoading ? (
              <LoadingState label="Reading syntax-aware chunks" />
            ) : chunksError ? (
              <ErrorState message={chunksError} />
            ) : !selectedPath ? (
              <EmptyState title="Select a file" detail="Choose an indexed source file to inspect its AST chunks." />
            ) : fileChunks?.chunks.length === 0 ? (
              <EmptyState title="This file has no AST chunks." detail="The indexer may classify it as unsupported or empty content." />
            ) : (
              <div className="ast-chunk-list">
                {fileChunks?.chunks.map((chunk, index) => (
                  <article className="ast-chunk" key={chunk.chunk_id}>
                    <header className="ast-chunk__header">
                      <div>
                        <span className="ast-chunk__index">{String(index + 1).padStart(2, '0')}</span>
                        <Badge tone="blue">L{chunk.start_line}-{chunk.end_line}</Badge>
                        <span className="ast-chunk__id">{chunk.chunk_id}</span>
                      </div>
                      <Badge>{formatNumber(chunk.estimated_tokens)} TOKENS</Badge>
                    </header>
                    <CodeBlock content={chunk.content} maxHeight={260} secretsRedacted={chunk.secrets_redacted} startLine={chunk.start_line} />
                    <div className="lexical-terms">
                      <span>BM25 TOKEN SAMPLE</span>
                      <div>
                        {chunk.bm25_tokens_preview.map((token) => <Badge key={token} tone="amber">{token}</Badge>)}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </Panel>
        </div>
      )}
    </div>
  );
}
