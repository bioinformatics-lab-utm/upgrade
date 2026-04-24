import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ScatterChart,
  Scatter,
  Treemap,
  ComposedChart,
  Area,
} from 'recharts';
import api from '../services/api';
import './PipelineResultsDashboard.css';

const COLORS = {
  high: '#dc2626',
  medium: '#f59e0b',
  low: '#10b981',
  primary: '#3b82f6',
  secondary: '#8b5cf6',
  success: '#10b981',
  warning: '#f59e0b',
  danger: '#ef4444',
};

const formatNumber = (num) => {
  if (!num) return '0';
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
  return num.toLocaleString();
};

const formatBytes = (bytes) => {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round((bytes / Math.pow(k, i)) * 10) / 10 + ' ' + sizes[i];
};

export default function PipelineResultsDashboard() {
  const { sampleId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    fetchPipelineResults();
  }, [sampleId]);

  const fetchPipelineResults = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await api.get(`/api/pipeline/results/${sampleId}/pipeline-summary`);
      setData(response.data);
    } catch (err) {
      const errorMsg = err.response?.data?.error || err.message || 'Failed to fetch results';
      setError(errorMsg);
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="dashboard-loading">
        <div className="spinner"></div>
        <p>Analyzing genomic data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard-error">
        <div className="error-icon">⚠</div>
        <h3>Error Loading Results</h3>
        <p>{error}</p>
        <div className="error-actions">
          <button onClick={fetchPipelineResults} className="btn btn-primary">Retry</button>
          <button onClick={() => navigate('/results')} className="btn btn-secondary">Go Back</button>
        </div>
      </div>
    );
  }

  const {
    sample_name,
    quality_score,
    amr_risk_score,
    status,
    qc,
    assembly,
    mags,
    amr,
    taxonomy,
  } = data || {};

  // Best real bin for quality metrics: highest completeness with contamination < 10%
  const bestBin = (mags?.bins || []).find(b => b.contamination < 10 && b.completeness > 0)
    || (mags?.bins || []).find(b => b.contamination < 50 && b.completeness > 0)
    || (mags?.bins || [])[0]
    || {};

  // Prepare data for visualizations
  const qualityMetrics = [
    { name: 'QC Quality', value: qc?.quality_score || 0 },
    { name: 'Assembly Quality', value: assembly?.quality_score || 0 },
    { name: 'N50', value: Math.min((assembly?.n50 || 0) / 100000 * 100, 100) },
    { name: 'Completeness', value: bestBin.completeness || 0 },
    { name: 'Purity', value: bestBin.contamination != null ? Math.max(0, 100 - bestBin.contamination) : 0 },
  ];

  const amrRiskData = [
    { name: 'AMR Risk', value: amr_risk_score || 0, color: COLORS.high },
    { name: 'Safe', value: Math.max(100 - (amr_risk_score || 0), 0), color: COLORS.low },
  ];

  const qcMetricsData = qc ? [
    { metric: 'Read Count', value: qc.reads_count },
    { metric: 'Total Bases', value: qc.total_bases },
    { metric: 'Mean Quality', value: qc.mean_qual },
    { metric: 'Median Quality', value: qc.median_qual },
    { metric: 'Mean Length', value: qc.mean_length },
    { metric: 'Median Length', value: qc.median_length },
  ] : [];

  const assemblyStatsData = assembly ? [
    { stat: 'Total Length', value: assembly.total_length },
    { stat: 'Contigs', value: assembly.contigs },
    { stat: 'N50', value: assembly.n50 },
    { stat: 'Largest Contig', value: assembly.largest_contig },
  ] : [];

  // taxonomy.species (enriched) or fall back to taxonomy.organisms (simple)
  const taxSpecies = taxonomy?.species || (taxonomy?.organisms || []).map(o => ({
    ...o,
    bin: null,
    risk_level: 'low',
    pathogenicity: 'environmental',
    clinical_relevance: 'No specific clinical relevance identified',
  }));

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'qc', label: 'Quality Control' },
    { id: 'assembly', label: 'Assembly' },
    { id: 'mags', label: 'MAGs' },
    { id: 'amr', label: 'AMR Analysis' },
    { id: 'taxonomy', label: 'Taxonomy' },
  ];

  return (
    <div className="pipeline-dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <div className="header-content">
          <div className="header-title">
            <h1>Pipeline Results</h1>
            <p className="sample-id">{sample_name || sampleId}</p>
          </div>
          <div className="header-actions">
            <button onClick={() => navigate('/results')} className="btn btn-back">
              ← Back to Results
            </button>
          </div>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="metrics-grid">
        <div className="metric-card quality">
          <div className="metric-label">Quality Score</div>
          <div className="metric-value">{quality_score?.toFixed(1) || 0}</div>
          <div className="metric-bar">
            <div className="metric-bar-fill" style={{ width: `${quality_score || 0}%` }}></div>
          </div>
        </div>

        <div className="metric-card amr">
          <div className="metric-label">AMR Risk Score</div>
          <div className="metric-value">{amr_risk_score?.toFixed(1) || 0}</div>
          <div className={`risk-badge risk-${amr_risk_score > 70 ? 'high' : amr_risk_score > 30 ? 'medium' : 'low'}`}>
            {amr_risk_score > 70 ? 'High Risk' : amr_risk_score > 30 ? 'Medium Risk' : 'Low Risk'}
          </div>
        </div>

        <div className="metric-card mags">
          <div className="metric-label">Total MAGs</div>
          <div className="metric-value">{mags?.total_bins || mags?.total || 0}</div>
          <div className="metric-detail">
            High: {mags?.high_quality || 0} | Medium: {mags?.medium_quality || 0} | Low: {mags?.low_quality || 0}
          </div>
        </div>

        <div className="metric-card genes">
          <div className="metric-label">AMR Genes</div>
          <div className="metric-value">{amr?.total_genes || 0}</div>
          <div className="metric-detail">Detected resistance genes</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="dashboard-tabs">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'overview' && (
          <div className="overview-grid">
            {/* Quality Radar Chart - Takes 2 rows on left */}
            <div className="chart-card">
              <h3>Quality Metrics Overview</h3>
              <ResponsiveContainer width="100%" height={420}>
                <RadarChart data={qualityMetrics}>
                  <PolarGrid stroke="#e2e8f0" strokeWidth={1.5} />
                  <PolarAngleAxis dataKey="name" tick={{ fill: '#475569', fontSize: 13, fontWeight: 600 }} />
                  <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fill: '#64748b', fontWeight: 600 }} />
                  <Radar name="Quality Score" dataKey="value" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.5} strokeWidth={2} />
                  <Tooltip />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            {/* AMR Risk Pie Chart - Top right */}
            <div className="chart-card">
              <h3>AMR Risk Distribution</h3>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie
                    data={amrRiskData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  >
                    {amrRiskData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>

            {/* QC Summary - Bottom right */}
            <div className="info-card">
              <h3>QC Summary</h3>
              <div className="info-grid">
                <div className="info-item">
                  <span className="info-label">Total Reads</span>
                  <span className="info-value">{formatNumber(qc?.reads_count)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Total Bases</span>
                  <span className="info-value">{formatBytes(qc?.total_bases)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Mean Quality</span>
                  <span className="info-value">{qc?.mean_qual?.toFixed(1)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Mean Length</span>
                  <span className="info-value">{qc?.mean_length?.toFixed(0)} bp</span>
                </div>
              </div>
            </div>

            {/* Assembly Summary - Full width bottom */}
            <div className="info-card info-card-wide">
              <h3>Assembly Summary</h3>
              <div className="info-grid info-grid-wide">
                <div className="info-item">
                  <span className="info-label">Total Length</span>
                  <span className="info-value">{formatBytes(assembly?.total_length)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Contigs</span>
                  <span className="info-value">{formatNumber(assembly?.contigs)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">N50</span>
                  <span className="info-value">{formatBytes(assembly?.n50)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">N90</span>
                  <span className="info-value">{formatBytes(assembly?.n90)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Largest Contig</span>
                  <span className="info-value">{formatBytes(assembly?.largest_contig)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">GC Content</span>
                  <span className="info-value">{assembly?.gc_content?.toFixed(1)}%</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'qc' && (
          <div className="qc-content">
            <div className="chart-card full-width">
              <h3>QC Metrics Distribution</h3>
              <ResponsiveContainer width="100%" height={400}>
                <BarChart data={qcMetricsData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="metric" tick={{ fill: '#6b7280' }} />
                  <YAxis tick={{ fill: '#6b7280' }} />
                  <Tooltip />
                  <Bar dataKey="value" fill={COLORS.primary} radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-label">Total Reads</div>
                <div className="stat-value">{formatNumber(qc?.reads_count)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Total Bases</div>
                <div className="stat-value">{formatBytes(qc?.total_bases)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Mean Read Length</div>
                <div className="stat-value">{qc?.mean_length?.toFixed(0)} bp</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Median Read Length</div>
                <div className="stat-value">{qc?.median_length?.toFixed(0)} bp</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Mean Quality Score</div>
                <div className="stat-value">{qc?.mean_qual?.toFixed(1)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Median Quality Score</div>
                <div className="stat-value">{qc?.median_qual?.toFixed(1)}</div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'assembly' && (
          <div className="assembly-content">
            <div className="chart-card full-width">
              <h3>Assembly Statistics</h3>
              <ResponsiveContainer width="100%" height={400}>
                <BarChart data={assemblyStatsData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis type="number" tick={{ fill: '#6b7280' }} />
                  <YAxis type="category" dataKey="stat" tick={{ fill: '#6b7280' }} width={120} />
                  <Tooltip />
                  <Bar dataKey="value" fill={COLORS.secondary} radius={[0, 8, 8, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-label">Total Assembly Length</div>
                <div className="stat-value">{formatBytes(assembly?.total_length)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Number of Contigs</div>
                <div className="stat-value">{formatNumber(assembly?.contigs)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">N50</div>
                <div className="stat-value">{formatBytes(assembly?.n50)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">N90</div>
                <div className="stat-value">{formatBytes(assembly?.n90)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Largest Contig</div>
                <div className="stat-value">{formatBytes(assembly?.largest_contig)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">GC Content</div>
                <div className="stat-value">{assembly?.gc_content?.toFixed(1)}%</div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'mags' && (
          <div className="mags-content">
            <div className="stats-grid">
              <div className="stat-card quality-high">
                <div className="stat-label">High Quality MAGs</div>
                <div className="stat-value">{mags?.high_quality || 0}</div>
              </div>
              <div className="stat-card quality-medium">
                <div className="stat-label">Medium Quality MAGs</div>
                <div className="stat-value">{mags?.medium_quality || 0}</div>
              </div>
              <div className="stat-card quality-low">
                <div className="stat-label">Low Quality MAGs</div>
                <div className="stat-value">{mags?.low_quality || 0}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Total MAGs</div>
                <div className="stat-value">{mags?.total_bins || mags?.total || 0}</div>
              </div>
            </div>

            {mags?.bins && mags.bins.length > 0 ? (
              <div className="table-card">
                <h3>MAG Details</h3>
                <div className="table-wrapper">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Bin ID</th>
                        <th>Completeness (%)</th>
                        <th>Contamination (%)</th>
                        <th>Strain Heterogeneity (%)</th>
                        <th>Quality</th>
                      </tr>
                    </thead>
                    <tbody>
                      {mags.bins.map((bin, idx) => (
                        <tr key={idx}>
                          <td className="mono">{bin.bin_id}</td>
                          <td>
                            <span className={`value ${bin.completeness > 90 ? 'good' : bin.completeness > 50 ? 'medium' : 'low'}`}>
                              {bin.completeness?.toFixed(1)}
                            </span>
                          </td>
                          <td>
                            <span className={`value ${bin.contamination < 5 ? 'good' : bin.contamination < 10 ? 'medium' : 'bad'}`}>
                              {bin.contamination?.toFixed(1)}
                            </span>
                          </td>
                          <td>{bin.strain_heterogeneity?.toFixed(1)}</td>
                          <td>
                            <span className={`badge badge-${bin.completeness > 90 && bin.contamination < 5 ? 'high' : bin.completeness > 50 && bin.contamination < 10 ? 'medium' : 'low'}`}>
                              {bin.completeness > 90 && bin.contamination < 5 ? 'High' : bin.completeness > 50 && bin.contamination < 10 ? 'Medium' : 'Low'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="empty-state">
                <p>No MAG data available</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'amr' && (
          <div className="amr-content">
            <div className="stats-grid">
              <div className="stat-card amr-critical">
                <div className="stat-label">Critical AMR Genes</div>
                <div className="stat-value">{amr?.high_risk_genes || 0}</div>
              </div>
              <div className="stat-card amr-warning">
                <div className="stat-label">Warning AMR Genes</div>
                <div className="stat-value">{amr?.medium_risk_genes || 0}</div>
              </div>
              <div className="stat-card amr-total">
                <div className="stat-label">Total AMR Genes</div>
                <div className="stat-value">{amr?.total_genes || 0}</div>
              </div>
            </div>

            {amr?.genes && amr.genes.length > 0 ? (
              <div className="table-card">
                <h3>AMR Gene Details</h3>
                <div className="table-wrapper">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Gene</th>
                        <th>Identity (%)</th>
                        <th>Coverage (%)</th>
                        <th>Antibiotic Class</th>
                        <th>Mechanism</th>
                      </tr>
                    </thead>
                    <tbody>
                      {amr.genes.map((gene, idx) => (
                        <tr key={idx}>
                          <td className="mono bold">{gene.gene}</td>
                          <td>
                            <span className={`value ${gene.identity > 95 ? 'high' : gene.identity > 80 ? 'medium' : 'low'}`}>
                              {gene.identity?.toFixed(1)}
                            </span>
                          </td>
                          <td>
                            <span className={`value ${gene.coverage > 90 ? 'high' : gene.coverage > 70 ? 'medium' : 'low'}`}>
                              {gene.coverage?.toFixed(1)}
                            </span>
                          </td>
                          <td>{gene.antibiotic_class || 'Unknown'}</td>
                          <td>{gene.mechanism || 'Unknown'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="empty-state success">
                <div className="empty-icon">✓</div>
                <p>No AMR genes detected</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'taxonomy' && (
          <div className="taxonomy-content">
            {(taxonomy?.species || taxonomy?.organisms) && (taxonomy?.species || taxonomy?.organisms).length > 0 ? (
              <>
                {/* Risk Assessment Summary */}
                <div className="stats-grid">
                  <div className="stat-card risk-high">
                    <div className="stat-label">High Risk Pathogens</div>
                    <div className="stat-value">{taxonomy?.risk_assessment?.high || 0}</div>
                  </div>
                  <div className="stat-card risk-medium">
                    <div className="stat-label">Medium Risk</div>
                    <div className="stat-value">{taxonomy?.risk_assessment?.medium || 0}</div>
                  </div>
                  <div className="stat-card risk-low">
                    <div className="stat-label">Low Risk / Commensal</div>
                    <div className="stat-value">{taxonomy?.risk_assessment?.low || 0}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Total Species Identified</div>
                    <div className="stat-value">{taxSpecies?.length || 0}</div>
                  </div>
                </div>

                {/* Treemap - Hierarchical Abundance View */}
                <div className="chart-card full-width">
                  <h3>Species Abundance Treemap</h3>
                  <p style={{ fontSize: '14px', color: '#64748b', marginBottom: '10px' }}>
                    Size represents relative abundance. Color indicates pathogenicity risk.
                  </p>
                  <ResponsiveContainer width="100%" height={400}>
                    <Treemap
                      data={taxSpecies.map((s, idx) => ({
                        name: s.name.split(' ').slice(0, 2).join(' '),
                        size: s.abundance || 1,
                        fill: s.risk_level === 'high' ? '#ef4444' : s.risk_level === 'medium' ? '#f59e0b' : '#10b981',
                        abundance: s.abundance,
                        risk: s.risk_level,
                        fullName: s.name
                      }))}
                      dataKey="size"
                      aspectRatio={4/3}
                      stroke="#fff"
                      fill="#3b82f6"
                      content={({ x, y, width, height, name, fill, abundance, risk, fullName }) => {
                        if (width < 50 || height < 30) return null;
                        return (
                          <g>
                            <rect
                              x={x}
                              y={y}
                              width={width}
                              height={height}
                              style={{
                                fill,
                                stroke: '#fff',
                                strokeWidth: 2,
                                strokeOpacity: 1,
                              }}
                            />
                            {width > 80 && height > 40 && (
                              <>
                                <text
                                  x={x + width / 2}
                                  y={y + height / 2 - 8}
                                  textAnchor="middle"
                                  fill="#fff"
                                  fontSize={12}
                                  fontWeight="bold"
                                >
                                  {name}
                                </text>
                                <text
                                  x={x + width / 2}
                                  y={y + height / 2 + 10}
                                  textAnchor="middle"
                                  fill="#fff"
                                  fontSize={11}
                                >
                                  {abundance?.toFixed(1)}%
                                </text>
                              </>
                            )}
                          </g>
                        );
                      }}
                    />
                  </ResponsiveContainer>
                  <div style={{ marginTop: '10px', display: 'flex', gap: '15px', justifyContent: 'center', fontSize: '13px' }}>
                    <span><span style={{ display: 'inline-block', width: '12px', height: '12px', background: '#ef4444', marginRight: '5px' }}></span>High Risk</span>
                    <span><span style={{ display: 'inline-block', width: '12px', height: '12px', background: '#f59e0b', marginRight: '5px' }}></span>Medium Risk</span>
                    <span><span style={{ display: 'inline-block', width: '12px', height: '12px', background: '#10b981', marginRight: '5px' }}></span>Low Risk</span>
                  </div>
                </div>

                {/* Stacked Bar Chart - Distribution by Bins */}
                <div className="chart-card full-width">
                  <h3>Taxonomic Distribution by Bins</h3>
                  <p style={{ fontSize: '14px', color: '#64748b', marginBottom: '10px' }}>
                    Shows species composition within each MAG (Metagenome-Assembled Genome)
                  </p>
                  <ResponsiveContainer width="100%" height={400}>
                    <BarChart
                      data={(() => {
                        // Group by bins
                        const binMap = {};
                        taxSpecies.forEach(s => {
                          const bin = s.bin || 'Unknown';
                          if (!binMap[bin]) binMap[bin] = { bin, species: [] };
                          binMap[bin].species.push(s);
                        });
                        
                        // Create stacked data
                        const bins = Object.values(binMap).slice(0, 10);
                        return bins.map(b => {
                          const data = { bin: b.bin };
                          b.species.forEach((s, idx) => {
                            data[`species_${idx}`] = s.abundance;
                            data[`species_${idx}_name`] = s.name.split(' ').slice(0, 2).join(' ');
                          });
                          return data;
                        });
                      })()}
                      margin={{ bottom: 80 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis 
                        dataKey="bin" 
                        angle={-45}
                        textAnchor="end"
                        height={100}
                        tick={{ fill: '#6b7280', fontSize: 11 }}
                      />
                      <YAxis 
                        tick={{ fill: '#6b7280' }}
                        label={{ value: 'Abundance (%)', angle: -90, position: 'insideLeft' }}
                      />
                      <Tooltip 
                        content={({ active, payload, label }) => {
                          if (active && payload && payload.length) {
                            return (
                              <div style={{ background: 'white', padding: '10px', border: '1px solid #ccc', borderRadius: '4px', maxWidth: '250px' }}>
                                <p style={{ margin: 0, fontWeight: 'bold' }}>{label}</p>
                                {payload.map((p, i) => (
                                  <p key={i} style={{ margin: '3px 0', color: p.fill, fontSize: '12px' }}>
                                    {p.payload[`${p.dataKey}_name`] || p.dataKey}: {p.value?.toFixed(2)}%
                                  </p>
                                ))}
                              </div>
                            );
                          }
                          return null;
                        }}
                      />
                      {/* Dynamic bars for each species */}
                      {taxSpecies.slice(0, 10).map((_, idx) => (
                        <Bar 
                          key={idx}
                          dataKey={`species_${idx}`} 
                          stackId="a" 
                          fill={`hsl(${idx * 36}, 70%, 60%)`}
                        />
                      ))}
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {/* Horizontal Bar Chart - Top 10 Species */}
                <div className="chart-card full-width">
                  <h3>Top 10 Most Abundant Species</h3>
                  <ResponsiveContainer width="100%" height={400}>
                    <BarChart
                      data={taxSpecies.slice(0, 10).map(s => ({
                        name: s.name.length > 35 ? s.name.substring(0, 35) + '...' : s.name,
                        abundance: s.abundance,
                        risk: s.risk_level
                      }))} 
                      layout="vertical"
                      margin={{ left: 150 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis type="number" tick={{ fill: '#6b7280' }} label={{ value: 'Abundance (%)', position: 'bottom' }} />
                      <YAxis type="category" dataKey="name" tick={{ fill: '#6b7280', fontSize: 12 }} width={140} />
                      <Tooltip 
                        content={({ active, payload }) => {
                          if (active && payload && payload.length) {
                            return (
                              <div style={{ background: 'white', padding: '10px', border: '1px solid #ccc', borderRadius: '4px' }}>
                                <p style={{ margin: 0, fontWeight: 'bold' }}>{payload[0].payload.name}</p>
                                <p style={{ margin: '5px 0 0 0', color: '#3b82f6' }}>
                                  Abundance: {payload[0].value.toFixed(2)}%
                                </p>
                                <p style={{ margin: '5px 0 0 0', color: payload[0].payload.risk === 'high' ? '#ef4444' : '#10b981' }}>
                                  Risk: {payload[0].payload.risk}
                                </p>
                              </div>
                            );
                          }
                          return null;
                        }}
                      />
                      <Bar 
                        dataKey="abundance" 
                        radius={[0, 8, 8, 0]}
                      >
                        {taxSpecies.slice(0, 10).map((entry, index) => (
                          <Cell 
                            key={`cell-${index}`} 
                            fill={entry.risk_level === 'high' ? '#ef4444' : entry.risk_level === 'medium' ? '#f59e0b' : '#10b981'} 
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {/* Detailed Table */}
                <div className="table-card full-width">
                  <h3>Detailed Taxonomic Classification</h3>
                  <div className="table-wrapper">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Bin</th>
                          <th>Species</th>
                          <th>Abundance (%)</th>
                          <th>Pathogenicity</th>
                          <th>Risk Level</th>
                          <th>Clinical Relevance</th>
                        </tr>
                      </thead>
                      <tbody>
                        {taxSpecies.map((species, idx) => (
                          <tr key={idx}>
                            <td className="mono">{species.bin || 'N/A'}</td>
                            <td className="italic">{species.name}</td>
                            <td className="abundance">{species.abundance?.toFixed(2)}%</td>
                            <td>
                              <span className={`badge badge-${species.pathogenicity === 'pathogen' ? 'danger' : 'success'}`}>
                                {species.pathogenicity || 'Unknown'}
                              </span>
                            </td>
                            <td>
                              <span className={`badge badge-${species.risk_level || 'low'}`}>
                                {species.risk_level || 'Low'}
                              </span>
                            </td>
                            <td className="clinical-info">{species.clinical_relevance || 'No specific information'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            ) : (
              <div className="empty-state">
                <div className="empty-icon">🔬</div>
                <p>No taxonomy data available</p>
                <p style={{ fontSize: '14px', color: '#64748b', marginTop: '10px' }}>
                  Taxonomy analysis requires Kraken2 database. Run pipeline with Kraken2 enabled.
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
