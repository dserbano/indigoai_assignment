import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from 'react'
import './App.css'

type DocumentItem = {
  id: string
  filename: string
  tags: string[]
  upload_date: string
  chunk_count: number
  file_type?: string
  size_bytes?: number
}

type SearchResult = {
  chunk_id: string
  text: string
  score: number
  document_id: string
  filename: string
  tags: string[]
  page_number?: number | null
}

type SearchResponse = {
  results: SearchResult[]
  detail?: string
}

type AgentResponse = {
  answer: string
  sources: string[]
  detail?: string
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const API_BEARER_TOKEN = import.meta.env.VITE_API_BEARER_TOKEN || ''

const SUGGESTED_TAGS = ['compliance', 'onboarding', 'product', 'hr', 'faq', 'manual']

const buildHeaders = (extra?: HeadersInit): HeadersInit => {
  const headers = new Headers(extra || {})
  if (API_BEARER_TOKEN) {
    headers.set('Authorization', `Bearer ${API_BEARER_TOKEN}`)
  }
  return headers
}

const formatDate = (value: string) => {
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

const formatBytes = (bytes?: number) => {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

async function safeJson(res: Response) {
  try {
    return await res.json()
  } catch {
    return {}
  }
}

function App() {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [tags, setTags] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [selectedUploadTags, setSelectedUploadTags] = useState<string[]>([])
  const [customTagInput, setCustomTagInput] = useState('')
  const [uploadMessage, setUploadMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const [searchQuery, setSearchQuery] = useState('')
  const [searchMode, setSearchMode] = useState<'all' | 'tag' | 'document'>('all')
  const [selectedSearchTags, setSelectedSearchTags] = useState<string[]>([])
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([])
  const [topK, setTopK] = useState(5)
  const [searching, setSearching] = useState(false)
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [searchInfo, setSearchInfo] = useState<string | null>(null)

  const [agentQuestion, setAgentQuestion] = useState('')
  const [agentAnswer, setAgentAnswer] = useState<string | null>(null)
  const [agentSources, setAgentSources] = useState<string[]>([])
  const [askingAgent, setAskingAgent] = useState(false)

  const customTags = useMemo(() => {
    return customTagInput
      .split(',')
      .map((tag) => tag.trim().toLowerCase())
      .filter(Boolean)
      .filter((tag, index, arr) => arr.indexOf(tag) === index)
  }, [customTagInput])

  const uploadTags = useMemo(() => {
    return [...new Set([...selectedUploadTags, ...customTags])]
  }, [selectedUploadTags, customTags])

  const availableTags = useMemo(() => {
    return [...new Set([...SUGGESTED_TAGS, ...tags])].sort()
  }, [tags])

  const totalChunks = useMemo(
    () => documents.reduce((sum, doc) => sum + (doc.chunk_count || 0), 0),
    [documents]
  )

  const refreshAll = async () => {
    setLoading(true)
    setErrorMessage(null)

    try {
      const [docsRes, tagsRes] = await Promise.all([
        fetch(`${API_BASE}/api/documents`, {
          headers: buildHeaders(),
        }),
        fetch(`${API_BASE}/api/tags`, {
          headers: buildHeaders(),
        }),
      ])

      const docsData = await safeJson(docsRes)
      const tagsData = await safeJson(tagsRes)

      if (!docsRes.ok) {
        throw new Error(docsData?.detail || `Failed to load documents: ${docsRes.status}`)
      }

      if (!tagsRes.ok) {
        throw new Error(tagsData?.detail || `Failed to load tags: ${tagsRes.status}`)
      }

      setDocuments(Array.isArray(docsData) ? docsData : docsData.documents || [])
      setTags(Array.isArray(tagsData) ? tagsData : tagsData.tags || [])
    } catch (error: any) {
      setErrorMessage(error?.message || 'Failed to load data.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshAll()
  }, [])

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    setSelectedFile(e.target.files?.[0] || null)
  }

  const toggleUploadTag = (tag: string) => {
    setSelectedUploadTags((prev) =>
      prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag]
    )
  }

  const toggleSearchTag = (tag: string) => {
    setSelectedSearchTags((prev) =>
      prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag]
    )
  }

  const toggleSearchDocument = (docId: string) => {
    setSelectedDocumentIds((prev) =>
      prev.includes(docId) ? prev.filter((item) => item !== docId) : [...prev, docId]
    )
  }

  const handleUpload = async (e: FormEvent) => {
    e.preventDefault()

    setUploadMessage(null)
    setErrorMessage(null)

    if (!selectedFile) {
      setErrorMessage('Please select a PDF or TXT file.')
      return
    }

    const allowed = ['application/pdf', 'text/plain']
    const fileName = selectedFile.name.toLowerCase()

    if (
      !allowed.includes(selectedFile.type) &&
      !fileName.endsWith('.pdf') &&
      !fileName.endsWith('.txt')
    ) {
      setErrorMessage('Only PDF and TXT files are supported.')
      return
    }

    try {
      setSubmitting(true)

      const formData = new FormData()
      formData.append('file', selectedFile)
      formData.append('tags', JSON.stringify(uploadTags))

      const res = await fetch(`${API_BASE}/api/documents`, {
        method: 'POST',
        headers: buildHeaders(),
        body: formData,
      })

      const data = await safeJson(res)

      if (!res.ok) {
        throw new Error(data?.detail || 'Upload failed.')
      }

      setUploadMessage(data?.message || `Uploaded "${selectedFile.name}" successfully.`)
      setSelectedFile(null)
      setSelectedUploadTags([])
      setCustomTagInput('')
      setSearchInfo(null)

      const input = document.getElementById('file-input') as HTMLInputElement | null
      if (input) input.value = ''

      await refreshAll()
    } catch (error: any) {
      setErrorMessage(error?.message || 'Upload failed.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: string) => {
    const confirmed = window.confirm('Delete this document from the knowledge base?')
    if (!confirmed) return

    setDeletingId(id)
    setErrorMessage(null)
    setUploadMessage(null)

    try {
      const res = await fetch(`${API_BASE}/api/documents/${id}`, {
        method: 'DELETE',
        headers: buildHeaders(),
      })

      const data = await safeJson(res)

      if (!res.ok) {
        throw new Error(data?.detail || 'Delete failed.')
      }

      setUploadMessage(data?.message || 'Document deleted.')
      setSearchResults((prev) => prev.filter((item) => item.document_id !== id))
      await refreshAll()
    } catch (error: any) {
      setErrorMessage(error?.message || 'Delete failed.')
    } finally {
      setDeletingId(null)
    }
  }

  const handleSearch = async (e: FormEvent) => {
    e.preventDefault()

    setErrorMessage(null)
    setUploadMessage(null)
    setSearchInfo(null)

    if (!searchQuery.trim()) {
      setErrorMessage('Enter a search query.')
      return
    }

    if (searchMode === 'tag' && selectedSearchTags.length === 0) {
      setErrorMessage('Select at least one tag.')
      return
    }

    if (searchMode === 'document' && selectedDocumentIds.length === 0) {
      setErrorMessage('Select at least one document.')
      return
    }

    const normalizedTopK = Number.isFinite(topK) ? Math.max(1, Math.min(20, topK)) : 5

    const payload =
      searchMode === 'all'
        ? { query: searchQuery.trim(), top_k: normalizedTopK, mode: 'all' }
        : searchMode === 'tag'
          ? {
              query: searchQuery.trim(),
              top_k: normalizedTopK,
              mode: 'tag',
              tags: selectedSearchTags,
            }
          : {
              query: searchQuery.trim(),
              top_k: normalizedTopK,
              mode: 'document',
              document_ids: selectedDocumentIds,
            }

    try {
      setSearching(true)

      const res = await fetch(`${API_BASE}/api/search`, {
        method: 'POST',
        headers: buildHeaders({
          'Content-Type': 'application/json',
        }),
        body: JSON.stringify(payload),
      })

      const data: SearchResponse = await safeJson(res)

      if (!res.ok) {
        throw new Error(data?.detail || 'Search failed.')
      }

      const results = Array.isArray(data?.results) ? data.results : []
      setSearchResults(results)
      setSearchInfo(results.length ? `Found ${results.length} results.` : 'No results found.')
    } catch (error: any) {
      setErrorMessage(error?.message || 'Search failed.')
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }

  const handleAskAgent = async (e: FormEvent) => {
    e.preventDefault()

    setErrorMessage(null)
    setUploadMessage(null)
    setSearchInfo(null)
    setAgentAnswer(null)
    setAgentSources([])

    if (!agentQuestion.trim()) {
      setErrorMessage('Enter a question for the AI.')
      return
    }

    try {
      setAskingAgent(true)

      const res = await fetch(`${API_BASE}/api/agent/ask`, {
        method: 'POST',
        headers: buildHeaders({
          'Content-Type': 'application/json',
        }),
        body: JSON.stringify({ question: agentQuestion.trim() }),
      })

      const data: AgentResponse = await safeJson(res)

      if (!res.ok) {
        throw new Error(data?.detail || 'Agent request failed.')
      }

      setAgentAnswer(data.answer || '')
      setAgentSources(Array.isArray(data.sources) ? data.sources : [])
    } catch (error: any) {
      setErrorMessage(error?.message || 'Agent request failed.')
    } finally {
      setAskingAgent(false)
    }
  }

  return (
    <div className="page">
      <div className="paper">
        <header className="topbar">
          <div>
            <p className="kicker">AI Solutions Engineer Assignment</p>
            <h1>Document Intelligence</h1>
            <p className="subtitle">
              Minimal white UI for upload, tags, search, and grounded AI answers.
            </p>
          </div>

          <div className="topbar-stats">
            <div className="mini-stat">
              <span>Documents</span>
              <strong>{documents.length}</strong>
            </div>
            <div className="mini-stat">
              <span>Tags</span>
              <strong>{tags.length}</strong>
            </div>
            <div className="mini-stat">
              <span>Chunks</span>
              <strong>{totalChunks}</strong>
            </div>
          </div>
        </header>

        {(errorMessage || uploadMessage || searchInfo) && (
          <div className="messages">
            {errorMessage && <div className="message message--error">{errorMessage}</div>}
            {uploadMessage && <div className="message message--success">{uploadMessage}</div>}
            {searchInfo && <div className="message message--info">{searchInfo}</div>}
          </div>
        )}

        <section className="grid grid--top">
          <section className="card">
            <div className="card-head">
              <h2>Upload</h2>
              <p>PDF or TXT with assignment-style tags.</p>
            </div>

            <form onSubmit={handleUpload} className="stack">
              <label className="field">
                <span>File</span>
                <input
                  id="file-input"
                  type="file"
                  accept=".pdf,.txt,application/pdf,text/plain"
                  onChange={handleFileChange}
                />
              </label>

              <div className="field">
                <span>Suggested tags</span>
                <div className="chips">
                  {SUGGESTED_TAGS.map((tag) => (
                    <button
                      key={tag}
                      type="button"
                      className={`chip ${selectedUploadTags.includes(tag) ? 'chip--active' : ''}`}
                      onClick={() => toggleUploadTag(tag)}
                    >
                      {tag}
                    </button>
                  ))}
                </div>
              </div>

              <label className="field">
                <span>Extra tags</span>
                <input
                  type="text"
                  value={customTagInput}
                  onChange={(e) => setCustomTagInput(e.target.value)}
                  placeholder="team-a, policies, support"
                />
              </label>

              {uploadTags.length > 0 && (
                <div className="field">
                  <span>Selected</span>
                  <div className="chips">
                    {uploadTags.map((tag) => (
                      <span key={tag} className="tag">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <button className="button" type="submit" disabled={submitting}>
                {submitting ? 'Uploading…' : 'Upload document'}
              </button>
            </form>
          </section>

          <section className="card">
            <div className="card-head">
              <h2>Search</h2>
              <p>Test semantic retrieval across all docs, by tag, or by document.</p>
            </div>

            <form onSubmit={handleSearch} className="stack">
              <label className="field">
                <span>Query</span>
                <textarea
                  rows={4}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="What does the onboarding policy say about compliance training?"
                />
              </label>

              <div className="row">
                <label className="field">
                  <span>Mode</span>
                  <select
                    value={searchMode}
                    onChange={(e) =>
                      setSearchMode(e.target.value as 'all' | 'tag' | 'document')
                    }
                  >
                    <option value="all">All documents</option>
                    <option value="tag">By tag</option>
                    <option value="document">By document</option>
                  </select>
                </label>

                <label className="field field--small">
                  <span>Top K</span>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={topK}
                    onChange={(e) => setTopK(Number(e.target.value))}
                  />
                </label>
              </div>

              {searchMode === 'tag' && (
                <div className="field">
                  <span>Tags</span>
                  <div className="chips">
                    {availableTags.length === 0 ? (
                      <p className="muted">No tags yet.</p>
                    ) : (
                      availableTags.map((tag) => (
                        <button
                          key={tag}
                          type="button"
                          className={`chip ${selectedSearchTags.includes(tag) ? 'chip--active' : ''}`}
                          onClick={() => toggleSearchTag(tag)}
                        >
                          {tag}
                        </button>
                      ))
                    )}
                  </div>
                </div>
              )}

              {searchMode === 'document' && (
                <div className="field">
                  <span>Documents</span>
                  <div className="list-select">
                    {documents.length === 0 ? (
                      <p className="muted">No documents yet.</p>
                    ) : (
                      documents.map((doc) => (
                        <label key={doc.id} className="check-row">
                          <input
                            type="checkbox"
                            checked={selectedDocumentIds.includes(doc.id)}
                            onChange={() => toggleSearchDocument(doc.id)}
                          />
                          <span>{doc.filename}</span>
                        </label>
                      ))
                    )}
                  </div>
                </div>
              )}

              <button className="button" type="submit" disabled={searching}>
                {searching ? 'Searching…' : 'Run search'}
              </button>
            </form>
          </section>
        </section>

        <section className="card">
          <div className="card-head">
            <h2>Ask AI</h2>
            <p>Use your grounded agent endpoint.</p>
          </div>

          <form onSubmit={handleAskAgent} className="stack">
            <label className="field">
              <span>Question</span>
              <textarea
                rows={4}
                value={agentQuestion}
                onChange={(e) => setAgentQuestion(e.target.value)}
                placeholder="What do the documents say about mandatory compliance training?"
              />
            </label>

            <button className="button" type="submit" disabled={askingAgent}>
              {askingAgent ? 'Thinking…' : 'Ask AI'}
            </button>
          </form>

          {agentAnswer && (
            <div className="answer">
              <h3>Answer</h3>
              <p>{agentAnswer}</p>

              {agentSources.length > 0 && (
                <>
                  <h4>Sources</h4>
                  <div className="chips">
                    {agentSources.map((source) => (
                      <span key={source} className="tag">
                        {source}
                      </span>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </section>

        <section className="grid">
          <section className="card">
            <div className="card-head">
              <h2>Documents</h2>
              <p>Uploaded files and assigned tags.</p>
            </div>

            {loading ? (
              <div className="empty">Loading…</div>
            ) : documents.length === 0 ? (
              <div className="empty">No documents uploaded yet.</div>
            ) : (
              <div className="doc-list">
                {documents.map((doc) => (
                  <article key={doc.id} className="doc-item">
                    <div className="doc-top">
                      <div>
                        <h3>{doc.filename}</h3>
                        <p className="meta">Uploaded {formatDate(doc.upload_date)}</p>
                      </div>

                      <div className="doc-actions">
                        <a
                          className="button button--ghost"
                          href={`${API_BASE}/api/documents/${doc.id}/download`}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          Download
                        </a>
                        <button
                          className="button button--danger"
                          onClick={() => handleDelete(doc.id)}
                          disabled={deletingId === doc.id}
                        >
                          {deletingId === doc.id ? 'Deleting…' : 'Delete'}
                        </button>
                      </div>
                    </div>

                    <div className="meta-row">
                      <span>{doc.chunk_count} chunks</span>
                      <span>{doc.file_type || 'unknown'}</span>
                      <span>{formatBytes(doc.size_bytes)}</span>
                    </div>

                    <div className="chips">
                      {doc.tags.length > 0 ? (
                        doc.tags.map((tag) => (
                          <span key={`${doc.id}-${tag}`} className="tag">
                            {tag}
                          </span>
                        ))
                      ) : (
                        <span className="muted">No tags</span>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="card">
            <div className="card-head">
              <h2>Results</h2>
              <p>Top retrieved chunks with provenance.</p>
            </div>

            {searchResults.length === 0 ? (
              <div className="empty">Run a search to see results.</div>
            ) : (
              <div className="result-list">
                {searchResults.map((result) => (
                  <article key={result.chunk_id} className="result-item">
                    <div className="result-top">
                      <div>
                        <h3>{result.filename}</h3>
                        <p className="meta">
                          Score {result.score.toFixed(4)}
                          {typeof result.page_number === 'number'
                            ? ` · Page ${result.page_number}`
                            : ''}
                        </p>
                      </div>
                      <span className="result-id">{result.chunk_id}</span>
                    </div>

                    <div className="chips">
                      {result.tags.map((tag) => (
                        <span key={`${result.chunk_id}-${tag}`} className="tag">
                          {tag}
                        </span>
                      ))}
                    </div>

                    <p className="result-text">{result.text}</p>
                  </article>
                ))}
              </div>
            )}
          </section>
        </section>

        <section className="card">
          <div className="card-head">
            <h2>Available Tags</h2>
            <p>These are the tags currently in the knowledge base.</p>
          </div>

          <div className="chips">
            {availableTags.length === 0 ? (
              <span className="muted">No tags available.</span>
            ) : (
              availableTags.map((tag) => (
                <span key={tag} className="tag">
                  {tag}
                </span>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  )
}

export default App