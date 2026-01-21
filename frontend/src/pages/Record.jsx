import { useState, useRef } from 'react'
import axios from 'axios'

function Record() {
  const [file, setFile] = useState(null)
  const [cameraId, setCameraId] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [hash, setHash] = useState(null)
  const fileInputRef = useRef(null)

  // Calculate hash client-side for preview
  const calculateHash = async (file) => {
    const buffer = await file.arrayBuffer()
    const hashBuffer = await crypto.subtle.digest('SHA-256', buffer)
    const hashArray = Array.from(new Uint8Array(hashBuffer))
    const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
    return '0x' + hashHex
  }

  const handleFileChange = async (e) => {
    const selectedFile = e.target.files[0]
    if (selectedFile) {
      setFile(selectedFile)
      setResult(null)
      setError(null)

      // Calculate and show hash
      try {
        const calculatedHash = await calculateHash(selectedFile)
        setHash(calculatedHash)
      } catch (err) {
        console.error('Hash calculation error:', err)
      }
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()

    if (!file) {
      setError('Please select a video file')
      return
    }

    if (!cameraId.trim()) {
      setError('Please enter a camera ID')
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const formData = new FormData()
      formData.append('video', file)
      formData.append('cameraId', cameraId.trim())

      const response = await axios.post('/api/record', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      })

      setResult(response.data)
      // Clear form on success
      setFile(null)
      setCameraId('')
      setHash(null)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    } catch (err) {
      setError(err.response?.data?.error || err.message)
    } finally {
      setLoading(false)
    }
  }

  const truncateHash = (hash) => {
    if (!hash) return '-'
    return `${hash.slice(0, 18)}...${hash.slice(-16)}`
  }

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Record Evidence</h1>

      <form onSubmit={handleSubmit} className="bg-white shadow-md rounded-lg p-6">
        {/* File Upload */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Video File
          </label>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept="video/*,.mp4,.avi,.mov,.mkv"
            className="block w-full text-sm text-gray-500
              file:mr-4 file:py-2 file:px-4
              file:rounded-md file:border-0
              file:text-sm file:font-semibold
              file:bg-blue-50 file:text-blue-700
              hover:file:bg-blue-100"
          />
          {file && (
            <p className="mt-2 text-sm text-gray-500">
              Selected: {file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)
            </p>
          )}
        </div>

        {/* Hash Preview */}
        {hash && (
          <div className="mb-6 p-4 bg-gray-50 rounded-lg">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Calculated SHA-256 Hash
            </label>
            <code className="block text-xs text-gray-600 break-all">
              {hash}
            </code>
          </div>
        )}

        {/* Camera ID */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Camera ID
          </label>
          <input
            type="text"
            value={cameraId}
            onChange={(e) => setCameraId(e.target.value)}
            placeholder="e.g., CAM-001, Entrance-Main"
            className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm
              focus:outline-none focus:ring-blue-500 focus:border-blue-500"
          />
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
            {error}
          </div>
        )}

        {/* Submit Button */}
        <button
          type="submit"
          disabled={loading || !file || !cameraId.trim()}
          className="w-full py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium
            text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2
            focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? 'Recording to Blockchain...' : 'Record Evidence'}
        </button>
      </form>

      {/* Success Result */}
      {result && (
        <div className="mt-6 bg-green-50 border border-green-400 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-green-800 mb-4">
            Evidence Recorded Successfully
          </h2>
          <dl className="space-y-2">
            <div>
              <dt className="text-sm font-medium text-gray-500">Video Hash</dt>
              <dd className="text-sm text-gray-900 break-all">
                <code>{result.videoHash}</code>
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Transaction Hash</dt>
              <dd className="text-sm text-gray-900 break-all">
                <code>{result.txHash}</code>
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Block Number</dt>
              <dd className="text-sm text-gray-900">{result.blockNumber}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Camera ID</dt>
              <dd className="text-sm text-gray-900">{result.cameraId}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Timestamp</dt>
              <dd className="text-sm text-gray-900">
                {new Date(result.timestamp * 1000).toLocaleString()}
              </dd>
            </div>
          </dl>
        </div>
      )}
    </div>
  )
}

export default Record
