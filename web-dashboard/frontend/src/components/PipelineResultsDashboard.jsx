import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Chip,
  Alert,
  AlertTitle,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Tabs,
  Tab,
  LinearProgress
} from '@mui/material';
import API from '../config/api';
import {
  Warning,
  CheckCircle,
  Error,
  Science,
  Biotech,
  LocalHospital
} from '@mui/icons-material';
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
  ScatterChart,
  Scatter,
  ZAxis
} from 'recharts';

const COLORS = {
  high: '#f44336',
  medium: '#ff9800',
  low: '#4caf50',
  excellent: '#4caf50',
  good: '#2196f3',
  poor: '#f44336'
};

function TabPanel({ children, value, index }) {
  return (
    <div hidden={value !== index}>
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

export default function PipelineResultsDashboard() {
  const { sampleId } = useParams();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tabValue, setTabValue] = useState(0);

  useEffect(() => {
    fetchPipelineResults();
  }, [sampleId]);

  const fetchPipelineResults = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API.API_BASE_URL}/api/pipeline/results/${sampleId}/pipeline-summary`);
      if (!response.ok) throw new Error('Failed to fetch results');
      const json = await response.json();
      setData(json);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error">
        <AlertTitle>Error</AlertTitle>
        {error}
      </Alert>
    );
  }

  return (
    <Box>
      {/* Executive Summary Card */}
      <Card sx={{ mb: 3, background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: 'white' }}>
        <CardContent>
          <Typography variant="h4" gutterBottom>
            Sample: {data.sample_id}
          </Typography>
          <Grid container spacing={3} sx={{ mt: 2 }}>
            <Grid item xs={12} md={3}>
              <Box textAlign="center">
                <Typography variant="h6">Quality Score</Typography>
                <Typography variant="h3">{data.quality_score}/100</Typography>
                <QualityBadge score={data.quality_score} />
              </Box>
            </Grid>
            <Grid item xs={12} md={3}>
              <Box textAlign="center">
                <Typography variant="h6">MAGs</Typography>
                <Typography variant="h3">{data.mags.total_bins}</Typography>
                <Typography variant="body2">
                  {data.mags.high_quality} high-quality
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} md={3}>
              <Box textAlign="center">
                <Typography variant="h6">AMR Risk</Typography>
                <Typography variant="h3">{data.amr_risk_score}/10</Typography>
                <RiskBadge score={data.amr_risk_score} />
              </Box>
            </Grid>
            <Grid item xs={12} md={3}>
              <Box textAlign="center">
                <Typography variant="h6">Pathogens</Typography>
                <Typography variant="h3">
                  {data.taxonomy.risk_assessment?.high || 0}
                </Typography>
                <Typography variant="body2">High-risk detected</Typography>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Alerts and Recommendations */}
      {data.amr_risk_score >= 7 && (
        <Alert severity="error" icon={<Error />} sx={{ mb: 2 }}>
          <AlertTitle>Critical AMR Risk</AlertTitle>
          <ul>
            <li>High-risk antibiotic resistance genes detected</li>
            <li>Immediate infection control measures recommended</li>
            <li>Consider carbapenem + colistin combination therapy</li>
          </ul>
        </Alert>
      )}

      {data.recommendations && data.recommendations.length > 0 && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              <LocalHospital /> Recommendations
            </Typography>
            {data.recommendations.map((rec, idx) => (
              <Alert 
                key={idx} 
                severity={rec.includes('🔴') ? 'error' : rec.includes('🟡') ? 'warning' : 'info'}
                sx={{ mb: 1 }}
              >
                {rec}
              </Alert>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Tabs for detailed views */}
      <Card>
        <Tabs value={tabValue} onChange={(e, v) => setTabValue(v)}>
          <Tab label="QC & Assembly" />
          <Tab label="MAG Quality" />
          <Tab label="Taxonomy" />
          <Tab label="AMR Analysis" />
          <Tab label="Functional" />
        </Tabs>

        {/* QC & Assembly Tab */}
        <TabPanel value={tabValue} index={0}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Typography variant="h6" gutterBottom>
                <Science /> QC Metrics
              </Typography>
              <TableContainer component={Paper}>
                <Table size="small">
                  <TableBody>
                    <TableRow>
                      <TableCell>Total Reads</TableCell>
                      <TableCell align="right">{data.qc.reads_count?.toLocaleString()}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>Total Bases</TableCell>
                      <TableCell align="right">
                        {(data.qc.total_bases / 1e6).toFixed(1)} Mb
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>Mean Read Length</TableCell>
                      <TableCell align="right">{data.qc.mean_length?.toFixed(0)} bp</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>Read N50</TableCell>
                      <TableCell align="right">{data.qc.n50?.toLocaleString()} bp</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>Mean Quality</TableCell>
                      <TableCell align="right">Q{data.qc.mean_quality?.toFixed(1)}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>Status</TableCell>
                      <TableCell align="right">
                        <Chip
                          label={data.qc.quality_status}
                          color={COLORS[data.qc.quality_status] ? 'success' : 'default'}
                          size="small"
                        />
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </TableContainer>
            </Grid>

            <Grid item xs={12} md={6}>
              <Typography variant="h6" gutterBottom>
                <Biotech /> Assembly Metrics
              </Typography>
              <TableContainer component={Paper}>
                <Table size="small">
                  <TableBody>
                    <TableRow>
                      <TableCell>Total Length</TableCell>
                      <TableCell align="right">
                        {(data.assembly.total_length / 1e6).toFixed(2)} Mb
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>Contigs</TableCell>
                      <TableCell align="right">{data.assembly.contigs_count}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>N50</TableCell>
                      <TableCell align="right">
                        {(data.assembly.n50 / 1000).toFixed(1)} kb
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>GC Content</TableCell>
                      <TableCell align="right">{data.assembly.gc_content?.toFixed(1)}%</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>Longest Contig</TableCell>
                      <TableCell align="right">
                        {(data.assembly.longest_contig / 1000).toFixed(1)} kb
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>Quality Score</TableCell>
                      <TableCell align="right">
                        <Box display="flex" alignItems="center" gap={1}>
                          <LinearProgress
                            variant="determinate"
                            value={data.assembly.quality_score}
                            sx={{ flexGrow: 1, height: 8, borderRadius: 4 }}
                          />
                          <Typography variant="body2">{data.assembly.quality_score}</Typography>
                        </Box>
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </TableContainer>
            </Grid>
          </Grid>
        </TabPanel>

        {/* MAG Quality Tab */}
        <TabPanel value={tabValue} index={1}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={4}>
              <Typography variant="h6" gutterBottom>
                Quality Distribution
              </Typography>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={[
                      { name: 'High', value: data.mags.high_quality },
                      { name: 'Medium', value: data.mags.medium_quality },
                      { name: 'Low', value: data.mags.low_quality }
                    ]}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="value"
                  >
                    <Cell fill={COLORS.high} />
                    <Cell fill={COLORS.medium} />
                    <Cell fill={COLORS.low} />
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </Grid>

            <Grid item xs={12} md={8}>
              <Typography variant="h6" gutterBottom>
                Completeness vs Contamination
              </Typography>
              <ResponsiveContainer width="100%" height={300}>
                <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                  <CartesianGrid />
                  <XAxis type="number" dataKey="completeness" name="Completeness" unit="%" />
                  <YAxis type="number" dataKey="contamination" name="Contamination" unit="%" />
                  <ZAxis type="number" range={[100, 400]} />
                  <Tooltip cursor={{ strokeDasharray: '3 3' }} />
                  <Legend />
                  <Scatter
                    name="High Quality"
                    data={data.mags.bins?.filter(b => b.quality === 'high')}
                    fill={COLORS.excellent}
                  />
                  <Scatter
                    name="Medium Quality"
                    data={data.mags.bins?.filter(b => b.quality === 'medium')}
                    fill={COLORS.medium}
                  />
                  <Scatter
                    name="Low Quality"
                    data={data.mags.bins?.filter(b => b.quality === 'low')}
                    fill={COLORS.poor}
                  />
                </ScatterChart>
              </ResponsiveContainer>
            </Grid>

            <Grid item xs={12}>
              <Typography variant="h6" gutterBottom>
                Top MAGs
              </Typography>
              <TableContainer component={Paper}>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Bin ID</TableCell>
                      <TableCell>Lineage</TableCell>
                      <TableCell align="right">Completeness</TableCell>
                      <TableCell align="right">Contamination</TableCell>
                      <TableCell align="right">Size (Mb)</TableCell>
                      <TableCell align="center">Quality</TableCell>
                      <TableCell align="center">Publication Ready</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {data.mags.bins?.slice(0, 10).map((bin) => (
                      <TableRow key={bin.id}>
                        <TableCell>{bin.id}</TableCell>
                        <TableCell>{bin.lineage}</TableCell>
                        <TableCell align="right">{bin.completeness.toFixed(1)}%</TableCell>
                        <TableCell align="right">{bin.contamination.toFixed(1)}%</TableCell>
                        <TableCell align="right">{bin.size_mb.toFixed(2)}</TableCell>
                        <TableCell align="center">
                          <Chip label={bin.quality} color={getQualityColor(bin.quality)} size="small" />
                        </TableCell>
                        <TableCell align="center">
                          {bin.publication_ready ? (
                            <CheckCircle color="success" />
                          ) : (
                            <Error color="error" />
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Grid>
          </Grid>
        </TabPanel>

        {/* Taxonomy Tab */}
        <TabPanel value={tabValue} index={2}>
          <Grid container spacing={3}>
            <Grid item xs={12}>
              <Typography variant="h6" gutterBottom>
                Detected Species
              </Typography>
              <TableContainer component={Paper}>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Bin</TableCell>
                      <TableCell>Species</TableCell>
                      <TableCell align="center">Pathogenicity</TableCell>
                      <TableCell align="center">Risk Level</TableCell>
                      <TableCell>Clinical Relevance</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {data.taxonomy.species?.map((sp) => (
                      <TableRow key={sp.bin}>
                        <TableCell>{sp.bin}</TableCell>
                        <TableCell><em>{sp.species}</em></TableCell>
                        <TableCell align="center">
                          <Chip
                            label={sp.pathogenicity}
                            color={sp.pathogenicity === 'pathogen' ? 'error' : 'default'}
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="center">
                          <Chip
                            label={sp.risk_level}
                            color={getQualityColor(sp.risk_level)}
                            size="small"
                          />
                        </TableCell>
                        <TableCell>{sp.clinical_relevance}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Grid>
          </Grid>
        </TabPanel>

        {/* AMR Analysis Tab */}
        <TabPanel value={tabValue} index={3}>
          <Grid container spacing={3}>
            <Grid item xs={12}>
              <Alert severity={data.amr_risk_score >= 7 ? 'error' : data.amr_risk_score >= 4 ? 'warning' : 'info'}>
                <AlertTitle>AMR Risk Score: {data.amr_risk_score}/10</AlertTitle>
                {data.amr.total_arg_genes} antibiotic resistance genes detected
                ({data.amr.high_risk} high-risk, {data.amr.moderate_risk} moderate-risk)
              </Alert>
            </Grid>

            <Grid item xs={12}>
              <Typography variant="h6" gutterBottom>
                Detected AMR Genes
              </Typography>
              <TableContainer component={Paper}>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Gene</TableCell>
                      <TableCell>Bin</TableCell>
                      <TableCell>Antibiotic</TableCell>
                      <TableCell align="center">Risk Level</TableCell>
                      <TableCell align="right">Identity</TableCell>
                      <TableCell align="right">Coverage</TableCell>
                      <TableCell>Database</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {data.amr.genes?.map((gene, idx) => (
                      <TableRow key={idx}>
                        <TableCell><strong>{gene.gene}</strong></TableCell>
                        <TableCell>{gene.bin}</TableCell>
                        <TableCell>{gene.antibiotic}</TableCell>
                        <TableCell align="center">
                          <Chip
                            label={gene.risk_level}
                            color={getQualityColor(gene.risk_level)}
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">{gene.identity?.toFixed(1)}%</TableCell>
                        <TableCell align="right">{gene.coverage?.toFixed(1)}%</TableCell>
                        <TableCell>{gene.database}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Grid>
          </Grid>
        </TabPanel>

        {/* Functional Tab */}
        <TabPanel value={tabValue} index={4}>
          <Typography variant="h6" gutterBottom>
            Functional Annotation
          </Typography>
          <Alert severity="info">
            Functional annotation results will be displayed here after implementing EggNOG-mapper and KofamScan modules.
          </Alert>
        </TabPanel>
      </Card>
    </Box>
  );
}

function QualityBadge({ score }) {
  if (score >= 90) return <Chip label="EXCELLENT" color="success" />;
  if (score >= 70) return <Chip label="GOOD" color="primary" />;
  return <Chip label="POOR" color="error" />;
}

function RiskBadge({ score }) {
  if (score >= 7) return <Chip label="CRITICAL" color="error" icon={<Error />} />;
  if (score >= 4) return <Chip label="HIGH" color="warning" icon={<Warning />} />;
  return <Chip label="LOW" color="success" icon={<CheckCircle />} />;
}

function getQualityColor(quality) {
  const map = {
    high: 'success',
    medium: 'primary',
    low: 'error',
    excellent: 'success',
    good: 'primary',
    poor: 'error'
  };
  return map[quality] || 'default';
}
