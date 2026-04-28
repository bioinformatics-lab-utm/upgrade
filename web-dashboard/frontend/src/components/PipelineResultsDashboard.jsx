import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
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
  ReferenceLine,
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

const PALETTE = [
  '#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444',
  '#06b6d4', '#f97316', '#84cc16', '#ec4899', '#6366f1',
];

// Format base-pair counts: 70860 → "70.9 Kbp", 11800000 → "11.8 Mbp"
const formatBp = (n) => {
  if (!n || n === 0) return '0 bp';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + ' Mbp';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + ' Kbp';
  return n + ' bp';
};

const formatNumber = (num) => {
  if (!num) return '0';
  if (num >= 1_000_000) return (num / 1_000_000).toFixed(1) + 'M';
  if (num >= 1_000) return (num / 1_000).toFixed(1) + 'K';
  return num.toLocaleString();
};

// Normalized 0-100 score for radar; uses log scale so large N50 values don't get capped
const n50RadarScore = (n50) => {
  if (!n50 || n50 <= 0) return 0;
  // log10 scale: 1bp=0, 1Kbp=~14, 10Kbp=~28, 100Kbp=~57, 1Mbp=~86, 10Mbp=100
  return Math.min(Math.log10(n50 + 1) / Math.log10(10_000_000) * 100, 100);
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
      setError(err.response?.data?.error || err.message || 'Failed to fetch results');
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

  const { sample_name, quality_score, amr_risk_score, status, qc, assembly, mags, amr, taxonomy } = data || {};

  const bestBin =
    (mags?.bins || []).find(b => b.contamination < 10 && b.completeness > 0) ||
    (mags?.bins || []).find(b => b.contamination < 50 && b.completeness > 0) ||
    (mags?.bins || [])[0] || {};

  // Radar data — all dimensions normalized 0-100
  const qualityMetrics = [
    { name: 'Read Quality', value: Math.min(((qc?.mean_qual || 0) / 20) * 100, 100) },
    { name: 'Assembly N50', value: n50RadarScore(assembly?.n50) },
    { name: 'Asm Quality', value: assembly?.quality_score || 0 },
    { name: 'Completeness', value: bestBin.completeness || 0 },
    { name: 'Purity', value: bestBin.contamination != null ? Math.max(0, 100 - bestBin.contamination * 5) : 0 },
  ];

  // AMR donut: high-risk vs moderate vs none
  const amrDonutData = [
    { name: 'High Risk', value: amr?.high_risk_genes || 0, color: COLORS.danger },
    { name: 'Moderate', value: amr?.medium_risk_genes || 0, color: COLORS.warning },
  ].filter(d => d.value > 0);
  if (amrDonutData.length === 0) amrDonutData.push({ name: 'No AMR genes', value: 1, color: COLORS.success });

  // AMR genes grouped by antibiotic class
  const amrByClass = {};
  (amr?.genes || []).forEach(g => {
    const cls = (g.antibiotic_class || 'Unknown').split(/[,;]/)[0].trim().slice(0, 40);
    if (!amrByClass[cls]) amrByClass[cls] = { class: cls, high: 0, moderate: 0 };
    if (g.risk_level === 'high') amrByClass[cls].high++;
    else amrByClass[cls].moderate++;
  });
  const amrClassData = Object.values(amrByClass).sort((a, b) => (b.high + b.moderate) - (a.high + a.moderate));

  // MAG scatter: completeness vs contamination
  const magScatterData = (mags?.bins || []).map(b => ({
    x: b.contamination || 0,
    y: b.completeness || 0,
    name: b.bin_id,
    quality: b.quality,
    color: b.quality === 'high' ? COLORS.success : b.quality === 'medium' ? COLORS.warning : COLORS.danger,
  }));

  // MAG quality donut
  const magQualityData = [
    { name: 'High Quality', value: mags?.high_quality || 0, color: COLORS.success },
    { name: 'Medium Quality', value: mags?.medium_quality || 0, color: COLORS.warning },
    { name: 'Low Quality', value: mags?.low_quality || 0, color: COLORS.danger },
  ].filter(d => d.value > 0);

  // N50 vs N90 chart
  const assemblyLengthData = [
    { name: 'N50', value: assembly?.n50 || 0 },
    { name: 'N90', value: assembly?.n90 || 0 },
    { name: 'Largest', value: assembly?.largest_contig || 0 },
  ];

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

  const amrRiskLevel = (amr_risk_score || 0) >= 7 ? 'high' : (amr_risk_score || 0) >= 3 ? 'medium' : 'low';
  const amrRiskLabel = amrRiskLevel === 'high' ? 'High Risk' : amrRiskLevel === 'medium' ? 'Medium Risk' : 'Low Risk';

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
            <button onClick={() => navigate('/results')} className="btn btn-back">← Back to Results</button>
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
          <div className="metric-label">AMR Risk (0–10)</div>
          <div className="metric-value">{amr_risk_score?.toFixed(1) || 0}</div>
          <div className={`risk-badge risk-${amrRiskLevel}`}>{amrRiskLabel}</div>
        </div>

        <div className="metric-card mags">
          <div className="metric-label">Total MAGs</div>
          <div className="metric-value">{mags?.total_bins || mags?.total || 0}</div>
          <div className="metric-detail">
            High: {mags?.high_quality || 0} | Med: {mags?.medium_quality || 0} | Low: {mags?.low_quality || 0}
          </div>
        </div>

        <div className="metric-card genes">
          <div className="metric-label">AMR Genes</div>
          <div className="metric-value">{amr?.total_genes || 0}</div>
          <div className="metric-detail">{amr?.high_risk_genes || 0} high-risk</div>
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

        {/* ─── OVERVIEW ─── */}
        {activeTab === 'overview' && (
          <div className="overview-grid">
            <div className="chart-card">
              <h3>Quality Metrics Overview</h3>
              <p style={{ fontSize: 13, color: '#64748b', marginBottom: 8 }}>
                All axes normalized 0–100. N50 on log₁₀ scale (100% ≈ 10 Mbp).
              </p>
              <ResponsiveContainer width="100%" height={380}>
                <RadarChart data={qualityMetrics}>
                  <PolarGrid stroke="#e2e8f0" strokeWidth={1.5} />
                  <PolarAngleAxis dataKey="name" tick={{ fill: '#475569', fontSize: 13, fontWeight: 600 }} />
                  <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fill: '#64748b', fontWeight: 600 }} />
                  <Radar name="Score" dataKey="value" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.45} strokeWidth={2} />
                  <Tooltip formatter={(v) => v.toFixed(1)} />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            <div className="chart-card">
              <h3>AMR Resistance Genes</h3>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie
                    data={amrDonutData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={4}
                    dataKey="value"
                    label={({ name, value }) => `${name}: ${value}`}
                    labelLine={false}
                  >
                    {amrDonutData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="info-card">
              <h3>
                QC Summary
                {qc?.quality_status && (
                  <span className={`badge badge-${qc.quality_status === 'excellent' ? 'success' : 'warning'}`}
                    style={{ marginLeft: 10 }}>
                    {qc.quality_status}
                  </span>
                )}
              </h3>
              <div className="info-grid">
                <div className="info-item">
                  <span className="info-label">Total Reads</span>
                  <span className="info-value">{formatNumber(qc?.reads_count)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Total Bases</span>
                  <span className="info-value">{formatBp(qc?.total_bases)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Mean Quality (Q)</span>
                  <span className="info-value">{qc?.mean_qual?.toFixed(1)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Mean Read Length</span>
                  <span className="info-value">{formatBp(qc?.mean_length)}</span>
                </div>
              </div>
            </div>

            <div className="info-card info-card-wide">
              <h3>Assembly Summary</h3>
              <div className="info-grid info-grid-wide">
                <div className="info-item">
                  <span className="info-label">Total Length</span>
                  <span className="info-value">{formatBp(assembly?.total_length)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Contigs</span>
                  <span className="info-value">{formatNumber(assembly?.contigs)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">N50</span>
                  <span className="info-value">{formatBp(assembly?.n50)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">N90</span>
                  <span className="info-value">{formatBp(assembly?.n90)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Largest Contig</span>
                  <span className="info-value">{formatBp(assembly?.largest_contig)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">GC Content</span>
                  <span className="info-value">{assembly?.gc_content?.toFixed(1)}%</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ─── QC ─── */}
        {activeTab === 'qc' && (
          <div className="qc-content">
            {/* Quality gauge cards */}
            <div className="gauge-grid">
              <div className="gauge-card">
                <div className="gauge-label">Mean Read Quality (Q)</div>
                <div className="gauge-value" style={{ color: (qc?.mean_qual || 0) >= 15 ? COLORS.success : (qc?.mean_qual || 0) >= 10 ? COLORS.warning : COLORS.danger }}>
                  Q{qc?.mean_qual?.toFixed(1) || '—'}
                </div>
                <div className="gauge-bar">
                  <div className="gauge-bar-fill" style={{
                    width: `${Math.min((qc?.mean_qual || 0) / 20 * 100, 100)}%`,
                    background: (qc?.mean_qual || 0) >= 15 ? COLORS.success : (qc?.mean_qual || 0) >= 10 ? COLORS.warning : COLORS.danger,
                  }} />
                </div>
                <div className="gauge-ref">Excellent ≥ Q15 &nbsp;·&nbsp; Good ≥ Q10</div>
              </div>

              <div className="gauge-card">
                <div className="gauge-label">Median Read Quality (Q)</div>
                <div className="gauge-value" style={{ color: (qc?.median_qual || 0) >= 15 ? COLORS.success : COLORS.warning }}>
                  Q{qc?.median_qual?.toFixed(1) || '—'}
                </div>
                <div className="gauge-bar">
                  <div className="gauge-bar-fill" style={{
                    width: `${Math.min((qc?.median_qual || 0) / 20 * 100, 100)}%`,
                    background: (qc?.median_qual || 0) >= 15 ? COLORS.success : COLORS.warning,
                  }} />
                </div>
                <div className="gauge-ref">Median ≥ Q15 preferred</div>
              </div>

              <div className="gauge-card">
                <div className="gauge-label">Mean Read Length</div>
                <div className="gauge-value">{formatBp(qc?.mean_length)}</div>
                <div className="gauge-bar">
                  <div className="gauge-bar-fill" style={{
                    width: `${Math.min((qc?.mean_length || 0) / 30000 * 100, 100)}%`,
                    background: COLORS.primary,
                  }} />
                </div>
                <div className="gauge-ref">ONT typical: 5–30 Kbp</div>
              </div>

              <div className="gauge-card">
                <div className="gauge-label">Read Length N50</div>
                <div className="gauge-value">{formatBp(qc?.n50)}</div>
                <div className="gauge-bar">
                  <div className="gauge-bar-fill" style={{
                    width: `${Math.min((qc?.n50 || 0) / 50000 * 100, 100)}%`,
                    background: COLORS.secondary,
                  }} />
                </div>
                <div className="gauge-ref">N50 read length</div>
              </div>
            </div>

            <div className="stats-grid" style={{ marginTop: 24 }}>
              <div className="stat-card">
                <div className="stat-label">Total Reads</div>
                <div className="stat-value">{formatNumber(qc?.reads_count)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Total Bases</div>
                <div className="stat-value">{formatBp(qc?.total_bases)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Mean Read Length</div>
                <div className="stat-value">{formatBp(qc?.mean_length)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Median Read Length</div>
                <div className="stat-value">{formatBp(qc?.median_length)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Mean Quality Score</div>
                <div className="stat-value">Q{qc?.mean_qual?.toFixed(1)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Median Quality Score</div>
                <div className="stat-value">Q{qc?.median_qual?.toFixed(1)}</div>
              </div>
            </div>
          </div>
        )}

        {/* ─── ASSEMBLY ─── */}
        {activeTab === 'assembly' && (
          <div className="assembly-content">
            {/* N50 / N90 / Largest chart — homogeneous unit: bp */}
            <div className="chart-card full-width">
              <h3>Contig Length Statistics (bp)</h3>
              <p style={{ fontSize: 13, color: '#64748b', marginBottom: 8 }}>
                N50: half the assembly is in contigs at least this long. N90: 90% threshold.
              </p>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={assemblyLengthData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis type="number" tick={{ fill: '#6b7280' }} tickFormatter={formatBp} />
                  <YAxis type="category" dataKey="name" tick={{ fill: '#475569', fontWeight: 600 }} width={70} />
                  <Tooltip formatter={(v) => formatBp(v)} />
                  <Bar dataKey="value" fill={COLORS.secondary} radius={[0, 8, 8, 0]}>
                    {assemblyLengthData.map((_, i) => (
                      <Cell key={i} fill={[COLORS.primary, COLORS.secondary, '#06b6d4'][i % 3]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-label">Total Assembly Length</div>
                <div className="stat-value">{formatBp(assembly?.total_length)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Number of Contigs</div>
                <div className="stat-value">{formatNumber(assembly?.contigs)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">N50</div>
                <div className="stat-value">{formatBp(assembly?.n50)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">N90</div>
                <div className="stat-value">{formatBp(assembly?.n90)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Largest Contig</div>
                <div className="stat-value">{formatBp(assembly?.largest_contig)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">GC Content</div>
                <div className="stat-value">{assembly?.gc_content?.toFixed(1)}%</div>
              </div>
            </div>
          </div>
        )}

        {/* ─── MAGs ─── */}
        {activeTab === 'mags' && (
          <div className="mags-content">
            <div className="mags-top-grid">
              {/* Quality donut */}
              <div className="chart-card">
                <h3>MAG Quality Distribution</h3>
                {magQualityData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={240}>
                    <PieChart>
                      <Pie
                        data={magQualityData}
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={90}
                        paddingAngle={4}
                        dataKey="value"
                        label={({ name, value }) => `${name}: ${value}`}
                      >
                        {magQualityData.map((d, i) => <Cell key={i} fill={d.color} />)}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="empty-state"><p>No MAG data</p></div>
                )}
              </div>

              {/* Completeness vs Contamination scatter — THE standard MAG QC plot */}
              <div className="chart-card">
                <h3>Completeness vs. Contamination</h3>
                <p style={{ fontSize: 13, color: '#64748b', marginBottom: 4 }}>
                  MIMAG thresholds: HQ ≥90% complete, &lt;5% contamination
                </p>
                {magScatterData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={260}>
                    <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis
                        type="number"
                        dataKey="x"
                        name="Contamination"
                        domain={[0, 'dataMax + 2']}
                        label={{ value: 'Contamination (%)', position: 'insideBottom', offset: -10 }}
                        tick={{ fill: '#6b7280' }}
                      />
                      <YAxis
                        type="number"
                        dataKey="y"
                        name="Completeness"
                        domain={[0, 100]}
                        label={{ value: 'Completeness (%)', angle: -90, position: 'insideLeft' }}
                        tick={{ fill: '#6b7280' }}
                      />
                      <Tooltip
                        cursor={{ strokeDasharray: '3 3' }}
                        content={({ active, payload }) => {
                          if (!active || !payload?.length) return null;
                          const d = payload[0].payload;
                          return (
                            <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 6, padding: '8px 12px', fontSize: 13 }}>
                              <strong>{d.name}</strong><br />
                              Completeness: {d.y.toFixed(1)}%<br />
                              Contamination: {d.x.toFixed(1)}%<br />
                              Quality: <span style={{ color: d.color, fontWeight: 600 }}>{d.quality}</span>
                            </div>
                          );
                        }}
                      />
                      {/* MIMAG HQ threshold lines */}
                      <ReferenceLine x={5} stroke="#dc2626" strokeDasharray="4 2" label={{ value: '5%', fill: '#dc2626', fontSize: 11 }} />
                      <ReferenceLine y={90} stroke="#10b981" strokeDasharray="4 2" label={{ value: '90%', fill: '#10b981', fontSize: 11 }} />
                      <Scatter
                        data={magScatterData}
                        shape={(props) => {
                          const { cx, cy, payload } = props;
                          return <circle cx={cx} cy={cy} r={8} fill={payload.color} fillOpacity={0.8} stroke="#fff" strokeWidth={1.5} />;
                        }}
                      />
                    </ScatterChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="empty-state"><p>No MAG scatter data</p></div>
                )}
              </div>
            </div>

            <div className="stats-grid" style={{ marginTop: 16 }}>
              <div className="stat-card quality-high">
                <div className="stat-label">High Quality MAGs</div>
                <div className="stat-value">{mags?.high_quality || 0}</div>
                <div className="stat-detail">≥90% complete, &lt;5% contam.</div>
              </div>
              <div className="stat-card quality-medium">
                <div className="stat-label">Medium Quality MAGs</div>
                <div className="stat-value">{mags?.medium_quality || 0}</div>
                <div className="stat-detail">≥50% complete, &lt;10% contam.</div>
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
              <div className="table-card" style={{ marginTop: 16 }}>
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
                            <span className={`badge badge-${bin.quality}`}>{bin.quality}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="empty-state"><p>No MAG data available</p></div>
            )}
          </div>
        )}

        {/* ─── AMR ─── */}
        {activeTab === 'amr' && (
          <div className="amr-content">
            <div className="stats-grid">
              <div className="stat-card amr-critical">
                <div className="stat-label">High-Risk Genes</div>
                <div className="stat-value">{amr?.high_risk_genes || 0}</div>
              </div>
              <div className="stat-card amr-warning">
                <div className="stat-label">Moderate-Risk Genes</div>
                <div className="stat-value">{amr?.medium_risk_genes || 0}</div>
              </div>
              <div className="stat-card amr-total">
                <div className="stat-label">Total AMR Genes</div>
                <div className="stat-value">{amr?.total_genes || 0}</div>
              </div>
            </div>

            {/* Antibiotic class distribution */}
            {amrClassData.length > 0 && (
              <div className="chart-card full-width" style={{ marginTop: 20 }}>
                <h3>Resistance by Antibiotic Class</h3>
                <p style={{ fontSize: 13, color: '#64748b', marginBottom: 8 }}>
                  Genes grouped by antibiotic class from the CARD database.
                </p>
                <ResponsiveContainer width="100%" height={Math.max(220, amrClassData.length * 36)}>
                  <BarChart data={amrClassData} layout="vertical" margin={{ left: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis type="number" allowDecimals={false} tick={{ fill: '#6b7280' }} />
                    <YAxis type="category" dataKey="class" width={180} tick={{ fill: '#475569', fontSize: 12 }} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="high" name="High Risk" stackId="a" fill={COLORS.danger} radius={[0, 0, 0, 0]} />
                    <Bar dataKey="moderate" name="Moderate" stackId="a" fill={COLORS.warning} radius={[0, 8, 8, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {amr?.genes && amr.genes.length > 0 ? (
              <div className="table-card full-width" style={{ marginTop: 20 }}>
                <h3>AMR Gene Details</h3>
                <div className="table-wrapper">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Gene</th>
                        <th>Identity (%)</th>
                        <th>Coverage (%)</th>
                        <th>Antibiotic Class</th>
                        <th>Risk</th>
                      </tr>
                    </thead>
                    <tbody>
                      {amr.genes.map((gene, idx) => (
                        <tr key={idx}>
                          <td className="mono bold">{gene.gene}</td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <div style={{ flex: 1, height: 6, background: '#e5e7eb', borderRadius: 3 }}>
                                <div style={{ width: `${gene.identity || 0}%`, height: '100%', background: gene.identity > 95 ? COLORS.success : COLORS.warning, borderRadius: 3 }} />
                              </div>
                              <span style={{ fontSize: 12, minWidth: 38 }}>{gene.identity?.toFixed(1)}%</span>
                            </div>
                          </td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <div style={{ flex: 1, height: 6, background: '#e5e7eb', borderRadius: 3 }}>
                                <div style={{ width: `${gene.coverage || 0}%`, height: '100%', background: COLORS.primary, borderRadius: 3 }} />
                              </div>
                              <span style={{ fontSize: 12, minWidth: 38 }}>{gene.coverage?.toFixed(1)}%</span>
                            </div>
                          </td>
                          <td style={{ fontSize: 13 }}>{gene.antibiotic_class || 'Unknown'}</td>
                          <td>
                            <span className={`badge badge-${gene.risk_level === 'high' ? 'danger' : 'warning'}`}>
                              {gene.risk_level || 'moderate'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="empty-state success" style={{ marginTop: 20 }}>
                <div className="empty-icon">✓</div>
                <p>No AMR genes detected</p>
              </div>
            )}
          </div>
        )}

        {/* ─── TAXONOMY ─── */}
        {activeTab === 'taxonomy' && (
          <div className="taxonomy-content">
            {taxSpecies.length > 0 ? (
              <>
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
                    <div className="stat-label">Total Species</div>
                    <div className="stat-value">{taxSpecies.length}</div>
                  </div>
                </div>

                {/* Treemap */}
                <div className="chart-card full-width">
                  <h3>Species Abundance Treemap</h3>
                  <p style={{ fontSize: 13, color: '#64748b', marginBottom: 8 }}>
                    Cell size = relative abundance. Red = pathogen, green = commensal.
                  </p>
                  <ResponsiveContainer width="100%" height={380}>
                    <Treemap
                      data={taxSpecies.map(s => ({
                        name: s.name.split(' ').slice(0, 2).join(' '),
                        size: s.abundance || 1,
                        fill: s.risk_level === 'high' ? '#ef4444' : s.risk_level === 'medium' ? '#f59e0b' : '#10b981',
                        abundance: s.abundance,
                        risk: s.risk_level,
                      }))}
                      dataKey="size"
                      aspectRatio={4 / 3}
                      stroke="#fff"
                      content={({ x, y, width, height, name, fill, abundance }) => {
                        if (width < 50 || height < 30) return null;
                        return (
                          <g>
                            <rect x={x} y={y} width={width} height={height} fill={fill} stroke="#fff" strokeWidth={2} />
                            {width > 80 && height > 40 && (
                              <>
                                <text x={x + width / 2} y={y + height / 2 - 6} textAnchor="middle" fill="#fff" fontSize={12} fontWeight="bold">{name}</text>
                                <text x={x + width / 2} y={y + height / 2 + 10} textAnchor="middle" fill="#fff" fontSize={11}>{abundance?.toFixed(1)}%</text>
                              </>
                            )}
                          </g>
                        );
                      }}
                    />
                  </ResponsiveContainer>
                  <div style={{ display: 'flex', gap: 16, justifyContent: 'center', fontSize: 13, marginTop: 8 }}>
                    {[['#ef4444', 'High Risk'], ['#f59e0b', 'Medium Risk'], ['#10b981', 'Low Risk']].map(([c, l]) => (
                      <span key={l}><span style={{ display: 'inline-block', width: 12, height: 12, background: c, marginRight: 5 }} />{l}</span>
                    ))}
                  </div>
                </div>

                {/* Top 10 horizontal bar */}
                <div className="chart-card full-width">
                  <h3>Top 10 Most Abundant Species</h3>
                  <ResponsiveContainer width="100%" height={380}>
                    <BarChart
                      data={taxSpecies.slice(0, 10).map(s => ({
                        name: s.name.length > 38 ? s.name.slice(0, 38) + '…' : s.name,
                        abundance: s.abundance,
                        risk: s.risk_level,
                      }))}
                      layout="vertical"
                      margin={{ left: 150 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis type="number" tick={{ fill: '#6b7280' }} label={{ value: 'Abundance (%)', position: 'insideBottom', offset: -5 }} />
                      <YAxis type="category" dataKey="name" tick={{ fill: '#6b7280', fontSize: 12 }} width={140} />
                      <Tooltip formatter={(v) => `${v.toFixed(2)}%`} />
                      <Bar dataKey="abundance" radius={[0, 8, 8, 0]}>
                        {taxSpecies.slice(0, 10).map((s, i) => (
                          <Cell key={i} fill={s.risk_level === 'high' ? '#ef4444' : s.risk_level === 'medium' ? '#f59e0b' : '#10b981'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {/* Detailed table */}
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
                          <th>Risk</th>
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
                                {species.risk_level || 'low'}
                              </span>
                            </td>
                            <td className="clinical-info">{species.clinical_relevance || '—'}</td>
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
                <p style={{ fontSize: 14, color: '#64748b', marginTop: 10 }}>
                  Taxonomy analysis requires the Kraken2 database. Run the pipeline with Kraken2 enabled.
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
