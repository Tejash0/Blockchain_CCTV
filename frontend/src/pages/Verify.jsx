import { useState, useRef } from 'react'
import axios from 'axios'

function Verify() {
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [hash, setHash] = useState(null)
  const [pHash, setPHash] = useState(null)
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef(null)

  const calculateHash = async (file) => {
    const buffer = await file.arrayBuffer()
    const hashBuffer = await crypto.subtle.digest('SHA-256', buffer)
    const hashArray = Array.from(new Uint8Array(hashBuffer))
    const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
    return '0x' + hashHex
  }

  const calculatePerceptualHash = async (file) => {
    const buffer = await file.arrayBuffer()
    const uint8 = new Uint8Array(buffer)
    const sampleSize = 4096
    const numSamples = 16
    const step = Math.max(1, Math.floor(uint8.length / numSamples))
    const chunks = []
    for (let i = 0; i < numSamples; i++) {
      const offset = Math.min(i * step, uint8.length - sampleSize)
      if (offset >= 0 && offset + sampleSize <= uint8.length) {
        chunks.push(uint8.slice(offset, offset + sampleSize))
      }
    }
    const combined = new Uint8Array(chunks.reduce((a, c) => a + c.length, 0))
    let pos = 0
    for (const chunk of chunks) { combined.set(chunk, pos); pos += chunk.length }
    const hashBuffer = await crypto.subtle.digest('SHA-256', combined)
    const hashArray = Array.from(new Uint8Array(hashBuffer))
    return '0x' + hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
  }

  const processFile = async (selectedFile) => {
    setFile(selectedFile)
    setResult(null)
    setError(null)
    try {
      const [calculatedHash, calculatedPHash] = await Promise.all([
        calculateHash(selectedFile),
        calculatePerceptualHash(selectedFile)
      ])
      setHash(calculatedHash)
      setPHash(calculatedPHash)
    } catch (err) {
      console.error('Hash calculation error:', err)
    }
  }

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0]
    if (selectedFile) processFile(selectedFile)
  }

  const handleDragOver = (e) => { e.preventDefault(); setIsDragging(true) }
  const handleDragLeave = (e) => { e.preventDefault(); setIsDragging(false) }
  const handleDrop = (e) => {
    e.preventDefault()
    setIsDragging(false)
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile) processFile(droppedFile)
  }

  const handleVerify = async () => {
    if (!file) { setError('Please select a file to verify'); return }
    setLoading(true); setError(null); setResult(null)
    try {
      const formData = new FormData()
      formData.append('video', file)
      const response = await axios.post('/api/verify', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setResult(response.data)
    } catch (err) {
      setError(err.response?.data?.error || err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleReset = () => {
    setFile(null); setHash(null); setPHash(null); setResult(null); setError(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const isZeroHash = (h) => !h || h === '0x' + '0'.repeat(64)
  const truncateHash = (h) => {
    if (isZeroHash(h)) return null
    return `${h.slice(0, 14)}...${h.slice(-10)}`
  }

  const hasDualHash = (evidence) =>
    evidence && !isZeroHash(evidence.reportHash) && !isZeroHash(evidence.videoHash)

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Verify Evidence</h1>

      {/* Drop Zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors
          ${isDragging ? 'border-blue-500 bg-blue-50'
            : file ? 'border-green-500 bg-green-50'
            : 'border-gray-300 hover:border-gray-400 bg-white'}`}
      >
        <input type="file" ref={fileInputRef} onChange={handleFileChange}
          accept="video/*,.mp4,.avi,.mov,.mkv" className="hidden" />
        {file ? (
          <div>
            <svg className="mx-auto h-12 w-12 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="mt-2 text-sm font-medium text-gray-900">{file.name}</p>
            <p className="text-xs text-gray-500">({(file.size / 1024 / 1024).toFixed(2)} MB)</p>
          </div>
        ) : (
          <div>
            <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <p className="mt-2 text-sm text-gray-600"><span className="font-semibold">Click to upload</span> or drag and drop</p>
            <p className="text-xs text-gray-500">Video files (MP4, AVI, MOV, MKV)</p>
          </div>
        )}
      </div>

      {/* Hash Preview */}
      {hash && (
        <div className="mt-4 p-4 bg-gray-50 rounded-lg space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">File SHA-256 Hash (Content Integrity)</label>
            <code className="block text-xs text-gray-600 break-all">{hash}</code>
          </div>
          {pHash && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Perceptual Hash (Visual Similarity)</label>
              <code className="block text-xs text-gray-600 break-all">{pHash}</code>
            </div>
          )}
        </div>
      )}

      {/* Action Buttons */}
      <div className="mt-6 flex space-x-4">
        <button onClick={handleVerify} disabled={loading || !file}
          className="flex-1 py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed">
          {loading ? 'Verifying...' : 'Verify on Blockchain'}
        </button>
        <button onClick={handleReset}
          className="px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50">
          Reset
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mt-6 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">{error}</div>
      )}

      {/* Verification Result */}
      {result && (
        <div className={`mt-6 border rounded-lg p-6 ${result.verified ? 'bg-green-50 border-green-400' : 'bg-red-50 border-red-400'}`}>
          {/* Status Banner */}
          <div className="flex items-center mb-4">
            {result.verified ? (
              <>
                <svg className="h-8 w-8 text-green-500 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                  <h2 className="text-lg font-bold text-green-800">VERIFIED</h2>
                  <p className="text-sm text-green-600">Evidence found on blockchain</p>
                </div>
                {hasDualHash(result.evidence) && (
                  <span className="ml-auto inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-indigo-100 text-indigo-800 border border-indigo-300">
                    Dual-Hash Verified
                  </span>
                )}
              </>
            ) : (
              <>
                <svg className="h-8 w-8 text-red-500 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                  <h2 className="text-lg font-bold text-red-800">NOT FOUND</h2>
                  <p className="text-sm text-red-600">{result.message || 'Evidence not found on blockchain'}</p>
                </div>
              </>
            )}
          </div>

          {/* Evidence Details */}
          {result.verified && result.evidence && (
            <dl className="space-y-2 border-t border-green-200 pt-4">
              <div>
                <dt className="text-sm font-medium text-gray-500">Video Hash (SHA-256)</dt>
                <dd className="text-sm text-gray-900 break-all"><code>{result.evidence.videoHash}</code></dd>
              </div>
              {!isZeroHash(result.evidence.perceptualHash) && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">Perceptual Hash (pHash)</dt>
                  <dd className="text-sm text-gray-900 break-all"><code>{truncateHash(result.evidence.perceptualHash)}</code></dd>
                </div>
              )}
              {!isZeroHash(result.evidence.reportHash) && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">Forensic Report Hash</dt>
                  <dd className="text-sm text-gray-900 break-all"><code>{truncateHash(result.evidence.reportHash)}</code></dd>
                  <dd className="text-xs text-gray-500 mt-1">SHA-256 of AI-generated forensic report, stored on-chain for provenance</dd>
                </div>
              )}
              <div>
                <dt className="text-sm font-medium text-gray-500">Camera ID</dt>
                <dd className="text-sm text-gray-900">{result.evidence.cameraId}</dd>
              </div>
              {result.evidence.eventType && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">Event Type</dt>
                  <dd className="text-sm text-gray-900 capitalize">{result.evidence.eventType}</dd>
                </div>
              )}
              {result.evidence.confidenceScore > 0 && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">Detection Confidence</dt>
                  <dd className="text-sm text-gray-900">{(result.evidence.confidenceScore / 100).toFixed(1)}%</dd>
                </div>
              )}
              {result.evidence.aiModelVersion && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">AI Model</dt>
                  <dd className="text-sm text-gray-900">{result.evidence.aiModelVersion}</dd>
                </div>
              )}
              <div>
                <dt className="text-sm font-medium text-gray-500">Recorded At</dt>
                <dd className="text-sm text-gray-900">{new Date(result.evidence.timestamp * 1000).toLocaleString()}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">Block Number</dt>
                <dd className="text-sm text-gray-900">{result.evidence.blockNumber}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">Uploader Address</dt>
                <dd className="text-sm text-gray-900 break-all"><code>{result.evidence.uploader}</code></dd>
              </div>
              {result.source && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">Verification Source</dt>
                  <dd className="text-sm text-gray-900">{result.source}</dd>
                </div>
              )}
            </dl>
          )}

          {/* Hash for not found */}
          {!result.verified && result.videoHash && (
            <div className="border-t border-red-200 pt-4">
              <dt className="text-sm font-medium text-gray-500">Searched Hash</dt>
              <dd className="text-sm text-gray-900 break-all"><code>{result.videoHash}</code></dd>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default Verify
