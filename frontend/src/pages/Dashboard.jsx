import { useState, useEffect } from 'react'
import axios from 'axios'

const EVENT_TYPE_COLORS = {
  violence: 'bg-red-100 text-red-800',
  theft: 'bg-orange-100 text-orange-800',
  vandalism: 'bg-yellow-100 text-yellow-800',
  intrusion: 'bg-purple-100 text-purple-800',
  manual: 'bg-gray-100 text-gray-800',
  manual_test: 'bg-blue-100 text-blue-800',
}

function Dashboard() {
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchLogs = async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await axios.get('/api/logs')
      setLogs(response.data.records || [])
    } catch (err) {
      setError(err.response?.data?.error || err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchLogs()
  }, [])

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp * 1000).toLocaleString()
  }

  const truncateHash = (hash) => {
    if (!hash || hash === '0x' + '0'.repeat(64)) return '-'
    return `${hash.slice(0, 10)}...${hash.slice(-8)}`
  }

  const truncateAddress = (address) => {
    if (!address) return '-'
    return `${address.slice(0, 6)}...${address.slice(-4)}`
  }

  const formatConfidence = (score) => {
    if (!score && score !== 0) return '-'
    return `${(score / 100).toFixed(1)}%`
  }

  const getEventBadge = (eventType) => {
    if (!eventType) return <span className="text-gray-400 text-xs">-</span>
    const colorClass = EVENT_TYPE_COLORS[eventType] || 'bg-gray-100 text-gray-800'
    return (
      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colorClass}`}>
        {eventType}
      </span>
    )
  }

  const getReportStatus = (reportHash) => {
    if (!reportHash || reportHash === '0x' + '0'.repeat(64)) {
      return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-500">N/A</span>
    }
    return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">Available</span>
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Evidence Dashboard</h1>
        <button
          onClick={fetchLogs}
          disabled={loading}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
          Error: {error}
        </div>
      )}

      <div className="bg-white shadow-md rounded-lg overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Video Hash</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Camera</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Event Type</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Confidence</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">AI Model</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Report</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Timestamp</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Block #</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Uploader</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan="9" className="px-6 py-4 text-center text-gray-500">
                  Loading evidence records...
                </td>
              </tr>
            ) : logs.length === 0 ? (
              <tr>
                <td colSpan="9" className="px-6 py-4 text-center text-gray-500">
                  No evidence records found. Start by recording some evidence.
                </td>
              </tr>
            ) : (
              logs.map((log, index) => (
                <tr key={log.videoHash || index} className="hover:bg-gray-50">
                  <td className="px-4 py-4 whitespace-nowrap">
                    <code className="text-sm text-gray-900 bg-gray-100 px-2 py-1 rounded">
                      {truncateHash(log.videoHash)}
                    </code>
                  </td>
                  <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-900">
                    {log.cameraId}
                  </td>
                  <td className="px-4 py-4 whitespace-nowrap">
                    {getEventBadge(log.eventType)}
                  </td>
                  <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-700">
                    {formatConfidence(log.confidenceScore)}
                  </td>
                  <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500">
                    {log.aiModelVersion || '-'}
                  </td>
                  <td className="px-4 py-4 whitespace-nowrap">
                    {getReportStatus(log.reportHash)}
                  </td>
                  <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500">
                    {formatTimestamp(log.timestamp)}
                  </td>
                  <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500">
                    {log.blockNumber || '-'}
                  </td>
                  <td className="px-4 py-4 whitespace-nowrap">
                    <code className="text-sm text-gray-500">
                      {truncateAddress(log.uploader)}
                    </code>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4 text-sm text-gray-500">
        Total records: {logs.length}
      </div>
    </div>
  )
}

export default Dashboard
