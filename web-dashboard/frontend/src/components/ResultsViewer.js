import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Container, Typography, Box, Paper, TextField, MenuItem,
  InputAdornment, CircularProgress, Alert, Button,
  Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, TablePagination, IconButton, Tooltip, Grid, Chip, Accordion,
  AccordionSummary, AccordionDetails, Slider, Stack, useMediaQuery,
  Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions, Snackbar
} from '@mui/material';
import {
  Assessment, Visibility, Download, Search, FilterList,
  CheckCircle, Error, Schedule, PlayArrow, Cancel,
  Place, CalendarToday, Science, Refresh, ExpandMore, Timer, DeleteOutline
} from '@mui/icons-material';
import api from '../services/api';
import './ResultsViewer.css';

const API_BASE_URL = '';

function ResultsViewer() {
  const navigate = useNavigate();
  const [runs, setRuns] = useState([]);
  const [filteredRuns, setFilteredRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [runtimeRange, setRuntimeRange] = useState([0, 500]);
  const [qualityRange, setQualityRange] = useState([0, 100]);
  const [magsRange, setMagsRange] = useState([0, 50]);
  const [amrRiskRange, setAmrRiskRange] = useState([0, 10]);
  const [page, setPage] = useState(0);
  // Run whose sample the user asked to delete (confirmation dialog open while set)
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [rowsPerPage, setRowsPerPage] = useState(50);
  // Below this width the table does not fit; runs are listed as cards instead
  const isMobile = useMediaQuery('(max-width:767.95px)');

  useEffect(() => {
    loadRuns();
    const interval = setInterval(loadRuns, 30000);
    return () => clearInterval(interval);
  }, [dateFrom, dateTo, runtimeRange, qualityRange, magsRange, amrRiskRange]);

  useEffect(() => {
    // Show only completed and failed runs
    let filtered = runs.filter(r => r.status === 'completed' || r.status === 'failed');
    
    if (statusFilter !== 'all') {
      filtered = filtered.filter(r => r.status === statusFilter);
    }
    
    if (searchQuery) {
      filtered = filtered.filter(r => 
        r.sample_code?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        r.location?.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        r.location?.city?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        r.pipeline_id?.toString().includes(searchQuery)
      );
    }
    setFilteredRuns(filtered);
    setPage(0);
  }, [runs, statusFilter, searchQuery]);

  const loadRuns = async () => {
    try {
      setLoading(true);
      const baseParams = new URLSearchParams();
      if (dateFrom) baseParams.append('date_from', dateFrom);
      if (dateTo) baseParams.append('date_to', dateTo);
      baseParams.append('limit', '2000');

      // Fetch completed and failed separately — API orders by started_at DESC,
      // so a single unfiltered call returns queued runs first and cuts off results.
      const [completedResp, failedResp] = await Promise.all([
        api.get(`${API_BASE_URL}/api/pipeline/runs?${baseParams}&status=completed`, { timeout: 30000 }),
        api.get(`${API_BASE_URL}/api/pipeline/runs?${baseParams}&status=failed`, { timeout: 30000 }),
      ]);

      const allRuns = [
        ...(completedResp.data.runs || []),
        ...(failedResp.data.runs || []),
      ].sort((a, b) => new Date(b.started_at || 0) - new Date(a.started_at || 0));

      setRuns(allRuns);
      setError(null);
    } catch (err) {
      setError(`Failed to load pipeline runs: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const deleteSample = async () => {
    const target = deleteTarget;
    setDeleting(true);
    setDeleteError(null);
    try {
      const { data } = await api.delete(`/api/samples/${target.sample_id}`);
      setRuns((list) => list.filter((r) => r.sample_id !== target.sample_id));
      setDeleteTarget(null);
      setNotice(`Sample ${data.sample_code} was deleted.`);
      // Header counts and other open views refresh from this
      window.dispatchEvent(new CustomEvent('upgrade:samples-changed'));
    } catch (err) {
      setDeleteError(err.response?.data?.error || 'Could not delete the sample. Please try again.');
    } finally {
      setDeleting(false);
    }
  };

  const handleClearFilters = () => {
    setDateFrom('');
    setDateTo('');
    setRuntimeRange([0, 500]);
    setQualityRange([0, 100]);
    setMagsRange([0, 50]);
    setAmrRiskRange([0, 10]);
    setStatusFilter('all');
    setSearchQuery('');
  };

  const getStatusColor = (s) => ({completed:'success',running:'info',failed:'error',queued:'warning'}[s]||'default');
  const getStatusIcon = (s) => ({completed:<CheckCircle/>,running:<PlayArrow/>,failed:<Error/>,queued:<Schedule/>}[s]||<Schedule/>);
  const formatDuration = (r) => {
    const m = r.runtime_minutes;
    if (m === null || m === undefined) return r.status === 'running' ? '⏱ Running...' : 'N/A';
    if (m < 1) return '< 1 min';
    return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m} min`;
  };
  const formatDate = (d) => d ? new Date(d).toLocaleString('en-US', {year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : 'N/A';

  if (loading) return <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px"><CircularProgress /></Box>;

  const paginatedRuns = filteredRuns.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);

  // Less important columns drop out as the table gets narrower
  const fromMd = { display: { xs: 'none', md: 'table-cell' } };
  const fromLg = { display: { xs: 'none', lg: 'table-cell' } };
  const columns = [
    { label: 'ID' }, { label: 'Sample' }, { label: 'Platform', sx: fromLg }, { label: 'Location', sx: fromMd },
    { label: 'Status' }, { label: 'Started' }, { label: 'Duration' }, { label: 'Actions' }
  ];

  const openRun = (r) => navigate(`/results/${r.sample_code||r.pipeline_id}`);
  const renderPlatform = (r) => <Chip icon={<Science/>} label={r.sequencing_platform||'Oxford Nanopore'} size="small" color="primary" variant="outlined" />;
  const renderStatus = (r) => <Chip icon={getStatusIcon(r.status)} label={r.status||'unknown'} color={getStatusColor(r.status)} size="small" sx={{minWidth:110,fontWeight:'medium',flexShrink:0}} />;
  const renderLocation = (r) => (
    <Box display="flex" alignItems="center">
      <Place fontSize="small" sx={{mr:0.5,color:'text.secondary'}} />
      <Tooltip title={[r.location.name, r.location.country].filter(Boolean).join(', ')}>
        <Typography variant="body2" noWrap sx={{maxWidth:150}}>{r.location.city||r.location.name}</Typography>
      </Tooltip>
    </Box>
  );
  const renderActions = (r) => (
    <>
      <Tooltip title="View Detailed Results"><IconButton size="small" color="primary" onClick={() => openRun(r)}><Visibility/></IconButton></Tooltip>
      <Tooltip title="Monitor Pipeline"><IconButton size="small" color="info" onClick={()=>navigate(`/pipeline/${r.pipeline_id}/monitor`)}><Assessment/></IconButton></Tooltip>
      {r.status === 'completed' && (
        <Tooltip title="Download PDF report">
          <IconButton size="small" color="secondary" aria-label={`Download PDF report of run ${r.pipeline_id}`}
            onClick={() => navigate(`/results/${r.pipeline_id}?download=pdf`)}>
            <Download/>
          </IconButton>
        </Tooltip>
      )}
      {r.sample_id && (
        <Tooltip title="Delete sample">
          <IconButton size="small" color="error" aria-label={`Delete sample ${r.sample_code}`}
            onClick={() => { setDeleteError(null); setDeleteTarget(r); }}>
            <DeleteOutline/>
          </IconButton>
        </Tooltip>
      )}
    </>
  );
  const emptyState = (
    <Box sx={{ py: 6, px: 2, textAlign: 'center' }}>
      <Assessment sx={{ fontSize: 60, color: 'text.secondary', mb: 2 }} />
      <Typography variant="h6" color="text.secondary">No Pipeline Runs Found</Typography>
      <Typography variant="body2" color="text.secondary">
        {searchQuery||statusFilter!=='all'?'Try adjusting filters':'Execute a pipeline to see results'}
      </Typography>
    </Box>
  );
  const pagination = (
    <TablePagination rowsPerPageOptions={[10, 25, 50, 100]} component="div" count={filteredRuns.length} rowsPerPage={rowsPerPage} page={page}
      labelRowsPerPage={isMobile ? 'Rows:' : undefined}
      sx={isMobile ? { '& .MuiTablePagination-toolbar': { px: 1 }, '& .MuiTablePagination-actions': { ml: 1 } } : undefined}
      onPageChange={(e,p)=>setPage(p)} onRowsPerPageChange={(e)=>{setRowsPerPage(+e.target.value);setPage(0);}} />
  );

  return (
    <Container maxWidth="xl" sx={{ mt: { xs: 1, md: 4 }, mb: 4, px: { xs: 0, md: 3 } }}>
      <Box sx={{ mb: { xs: 2, md: 4 } }}>
        <Typography variant="h4" sx={{ display: 'flex', alignItems: 'center', mb: 2, fontSize: { xs: '1.5rem', sm: '2.125rem' } }}>
          <Assessment sx={{ mr: { xs: 1, sm: 2 }, fontSize: { xs: 28, sm: 40 }, color: 'primary.main' }} />
          Pipeline Results & Reports
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Browse completed pipeline runs, download results, and view analysis reports
        </Typography>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>{error}</Alert>}

      <Paper elevation={2} sx={{ p: { xs: 2, sm: 3 }, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid size={{ xs: 12, md: 6 }}>
            <TextField fullWidth size="small" placeholder="Search by sample, location, or ID..."
              value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
              InputProps={{startAdornment: <InputAdornment position="start"><Search color="action" /></InputAdornment>}}
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <TextField fullWidth select size="small" label="Filter by Status"
              value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
              InputProps={{startAdornment: <InputAdornment position="start"><FilterList color="action" /></InputAdornment>}}
            >
              {['all','completed','failed'].map(s => <MenuItem key={s} value={s}>{s==='all'?'All Results':s.charAt(0).toUpperCase()+s.slice(1)}</MenuItem>)}
            </TextField>
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <Box display="flex" justifyContent={{ xs: 'space-between', md: 'flex-end' }} alignItems="center" gap={2}>
              <Typography variant="body2" color="text.secondary">{filteredRuns.length} run{filteredRuns.length!==1?'s':''}</Typography>
              <Button variant="outlined" startIcon={<Refresh />} onClick={loadRuns} size="small">Refresh</Button>
            </Box>
          </Grid>
        </Grid>
        
        <Accordion sx={{ mt: 2 }}>
          <AccordionSummary expandIcon={<ExpandMore />}>
            <Box display="flex" alignItems="center" gap={1}>
              <FilterList color="primary" />
              <Typography variant="subtitle1" fontWeight="medium">Advanced Filters</Typography>
              {(dateFrom || dateTo || runtimeRange[0] > 0 || runtimeRange[1] < 500 || 
                qualityRange[0] > 0 || qualityRange[1] < 100 || magsRange[0] > 0 || magsRange[1] < 50 ||
                amrRiskRange[0] > 0 || amrRiskRange[1] < 10) && (
                <Chip label="Active" color="primary" size="small" />
              )}
            </Box>
          </AccordionSummary>
          <AccordionDetails>
            <Grid container spacing={3}>
              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="subtitle2" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <CalendarToday fontSize="small" color="primary" />
                  Date Range
                </Typography>
                <Grid container spacing={2}>
                  <Grid size={6}>
                    <TextField fullWidth size="small" type="date" label="From" value={dateFrom}
                      onChange={(e) => setDateFrom(e.target.value)} InputLabelProps={{ shrink: true }} />
                  </Grid>
                  <Grid size={6}>
                    <TextField fullWidth size="small" type="date" label="To" value={dateTo}
                      onChange={(e) => setDateTo(e.target.value)} InputLabelProps={{ shrink: true }} />
                  </Grid>
                </Grid>
              </Grid>
              
              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="subtitle2" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Timer fontSize="small" color="primary" />
                  Runtime (minutes): {runtimeRange[0]} - {runtimeRange[1] === 500 ? '500+' : runtimeRange[1]}
                </Typography>
                <Box sx={{ px: 2, pt: 1 }}>
                  <Slider value={runtimeRange} onChange={(e, newValue) => setRuntimeRange(newValue)}
                    valueLabelDisplay="auto" min={0} max={500} step={5}
                    marks={[{value:0,label:'0'},{value:100,label:'100'},{value:200,label:'200'},{value:300,label:'300'},{value:400,label:'400'},{value:500,label:'500+'}]}
                  />
                </Box>
              </Grid>
              
              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="subtitle2" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Assessment fontSize="small" color="primary" />
                  Quality Score: {qualityRange[0]} - {qualityRange[1]}
                </Typography>
                <Box sx={{ px: 2, pt: 1 }}>
                  <Slider value={qualityRange} onChange={(e, newValue) => setQualityRange(newValue)}
                    valueLabelDisplay="auto" min={0} max={100} step={5}
                    marks={[{value:0,label:'0'},{value:25,label:'25'},{value:50,label:'50'},{value:75,label:'75'},{value:100,label:'100'}]}
                  />
                </Box>
              </Grid>
              
              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="subtitle2" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Science fontSize="small" color="primary" />
                  MAGs Count: {magsRange[0]} - {magsRange[1] === 50 ? '50+' : magsRange[1]}
                </Typography>
                <Box sx={{ px: 2, pt: 1 }}>
                  <Slider value={magsRange} onChange={(e, newValue) => setMagsRange(newValue)}
                    valueLabelDisplay="auto" min={0} max={50} step={1}
                    marks={[{value:0,label:'0'},{value:10,label:'10'},{value:20,label:'20'},{value:30,label:'30'},{value:40,label:'40'},{value:50,label:'50+'}]}
                  />
                </Box>
              </Grid>
              
              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="subtitle2" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Error fontSize="small" color="warning" />
                  AMR Risk Score: {amrRiskRange[0]} - {amrRiskRange[1] === 10 ? '10+' : amrRiskRange[1]}
                </Typography>
                <Box sx={{ px: 2, pt: 1 }}>
                  <Slider value={amrRiskRange} onChange={(e, newValue) => setAmrRiskRange(newValue)}
                    valueLabelDisplay="auto" min={0} max={10} step={1}
                    marks={[{value:0,label:'0'},{value:2,label:'2'},{value:4,label:'4'},{value:6,label:'6'},{value:8,label:'8'},{value:10,label:'10+'}]}
                  />
                </Box>
              </Grid>
              
              <Grid size={12}>
                <Box display="flex" justifyContent="flex-end" flexWrap="wrap" gap={2}>
                  <Button variant="outlined" onClick={handleClearFilters} size="small">Clear Filters</Button>
                  <Button variant="contained" onClick={loadRuns} size="small" startIcon={<FilterList />}>Apply Filters</Button>
                </Box>
              </Grid>
            </Grid>
          </AccordionDetails>
        </Accordion>
      </Paper>

      {isMobile ? (
        <Stack spacing={1.5}>
          {paginatedRuns.length === 0 ? <Paper elevation={2}>{emptyState}</Paper> : paginatedRuns.map((r) => (
            <Paper key={r.pipeline_id} elevation={2} sx={{ p: 2, cursor: 'pointer' }} onClick={() => openRun(r)}>
              <Box display="flex" justifyContent="space-between" alignItems="flex-start" gap={1}>
                <Box minWidth={0}>
                  <Typography variant="caption" fontWeight="medium" color="primary">#{r.pipeline_id}</Typography>
                  <Typography variant="body1" fontWeight="medium" sx={{ overflowWrap: 'anywhere', lineHeight: 1.3 }}>{r.sample_code||'Unknown'}</Typography>
                </Box>
                {renderStatus(r)}
              </Box>
              <Box display="flex" flexWrap="wrap" alignItems="center" gap={1} mt={1.5}>
                {renderPlatform(r)}
                {r.location && renderLocation(r)}
              </Box>
              <Box display="flex" justifyContent="space-between" alignItems="center" gap={1} mt={1}>
                <Typography variant="body2" color="text.secondary">{formatDate(r.started_at)} · {formatDuration(r)}</Typography>
                <Box flexShrink={0} onClick={(e)=>e.stopPropagation()}>{renderActions(r)}</Box>
              </Box>
            </Paper>
          ))}
          <Paper elevation={2}>{pagination}</Paper>
        </Stack>
      ) : (
        <TableContainer component={Paper} elevation={3}>
          <Table sx={{ '& .MuiTableCell-root': { px: { xs: 1.5, lg: 2 } } }}>
            <TableHead>
              <TableRow sx={{ backgroundColor: 'primary.main' }}>
                {columns.map(c =>
                  <TableCell key={c.label} sx={{ color: 'white', fontWeight: 'bold', ...c.sx }} align={c.label==='Actions'?'center':'left'}>{c.label}</TableCell>
                )}
              </TableRow>
            </TableHead>
            <TableBody>
              {paginatedRuns.length === 0 ? (
                <TableRow><TableCell colSpan={columns.length} align="center">{emptyState}</TableCell></TableRow>
              ) : paginatedRuns.map((r) => (
                <TableRow key={r.pipeline_id} hover sx={{'&:hover':{backgroundColor:'action.hover'},cursor:'pointer'}} onClick={() => openRun(r)}>
                  <TableCell><Typography variant="body2" fontWeight="medium" color="primary">#{r.pipeline_id}</Typography></TableCell>
                  <TableCell>
                    <Box>
                      <Typography variant="body2" fontWeight="medium" sx={{ overflowWrap: 'anywhere' }}>{r.sample_code||'Unknown'}</Typography>
                      {r.sample_type && <Chip label={r.sample_type} size="small" variant="outlined" sx={{mt:0.5,height:20,fontSize:'0.7rem'}} />}
                    </Box>
                  </TableCell>
                  <TableCell sx={fromLg}>{renderPlatform(r)}</TableCell>
                  <TableCell sx={fromMd}>
                    {r.location ? renderLocation(r) : <Typography variant="body2" color="text.secondary">N/A</Typography>}
                  </TableCell>
                  <TableCell>{renderStatus(r)}</TableCell>
                  <TableCell>
                    <Box display="flex" alignItems="center">
                      <CalendarToday fontSize="small" sx={{mr:0.5,color:'text.secondary',display:{xs:'none',lg:'block'}}} />
                      <Typography variant="body2" noWrap>{formatDate(r.started_at)}</Typography>
                    </Box>
                  </TableCell>
                  <TableCell><Typography variant="body2" fontWeight="medium" noWrap>{formatDuration(r)}</Typography></TableCell>
                  <TableCell align="center" sx={{ whiteSpace: 'nowrap' }} onClick={(e)=>e.stopPropagation()}>{renderActions(r)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {pagination}
        </TableContainer>
      )}

      <Dialog open={Boolean(deleteTarget)} onClose={() => !deleting && setDeleteTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete sample {deleteTarget?.sample_code}?</DialogTitle>
        <DialogContent>
          <DialogContentText component="div">
            This permanently deletes the sample and all its analysis runs, with their results, reports
            and the uploaded FASTQ files. It is also removed from the map.
            <Box component="strong" sx={{ display: 'block', mt: 1.5 }}>This cannot be undone.</Box>
          </DialogContentText>
          {deleteError && <Alert severity="error" sx={{ mt: 2 }}>{deleteError}</Alert>}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setDeleteTarget(null)} disabled={deleting}>Cancel</Button>
          <Button onClick={deleteSample} color="error" variant="contained" disabled={deleting}
            startIcon={deleting ? <CircularProgress size={16} color="inherit" /> : <DeleteOutline />}>
            {deleting ? 'Deleting…' : 'Delete sample'}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={Boolean(notice)} autoHideDuration={5000} onClose={() => setNotice(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        sx={{ bottom: { xs: 'calc(var(--footer-height) + 12px)', sm: 'calc(var(--footer-height) + 16px)' } }}>
        <Alert severity="success" variant="filled" onClose={() => setNotice(null)}>{notice}</Alert>
      </Snackbar>
    </Container>
  );
}

export default ResultsViewer;
