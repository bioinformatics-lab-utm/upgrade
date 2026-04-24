import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Container, Typography, Box, Paper, TextField, MenuItem,
  InputAdornment, CircularProgress, Alert, Button,
  Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, TablePagination, IconButton, Tooltip, Grid, Chip, Accordion,
  AccordionSummary, AccordionDetails, Slider
} from '@mui/material';
import {
  Assessment, Visibility, Download, Search, FilterList,
  CheckCircle, Error, Schedule, PlayArrow, Cancel,
  Place, CalendarToday, Science, Refresh, ExpandMore, Timer
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
  const [rowsPerPage, setRowsPerPage] = useState(50);

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
        r.pipeline_id?.toString().includes(searchQuery)
      );
    }
    setFilteredRuns(filtered);
    setPage(0);
  }, [runs, statusFilter, searchQuery]);

  const loadRuns = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (dateFrom) params.append('date_from', dateFrom);
      if (dateTo) params.append('date_to', dateTo);
      if (runtimeRange[0] > 0) params.append('min_runtime', runtimeRange[0]);
      if (runtimeRange[1] < 500) params.append('max_runtime', runtimeRange[1]);
      if (qualityRange[0] > 0) params.append('min_quality', qualityRange[0]);
      if (qualityRange[1] < 100) params.append('max_quality', qualityRange[1]);
      if (magsRange[0] > 0) params.append('min_mags', magsRange[0]);
      if (magsRange[1] < 50) params.append('max_mags', magsRange[1]);
      if (amrRiskRange[0] > 0) params.append('min_amr_risk', amrRiskRange[0]);
      if (amrRiskRange[1] < 10) params.append('max_amr_risk', amrRiskRange[1]);
      
      const url = `${API_BASE_URL}/api/pipeline/runs${params.toString() ? '?' + params.toString() : ''}`;
      const response = await api.get(url, { timeout: 10000 });
      setRuns(response.data.runs || []);
      setError(null);
    } catch (err) {
      setError(`Failed to load pipeline runs: ${err.message}`);
    } finally {
      setLoading(false);
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
  const formatDate = (d) => d ? new Date(d).toLocaleString('en-US', {year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : 'N/A';

  if (loading) return <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px"><CircularProgress /></Box>;

  const paginatedRuns = filteredRuns.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <Assessment sx={{ mr: 2, fontSize: 40, color: 'primary.main' }} />
          Pipeline Results & Reports
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Browse completed pipeline runs, download results, and view analysis reports
        </Typography>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>{error}</Alert>}

      <Paper elevation={2} sx={{ p: 3, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={6}>
            <TextField fullWidth size="small" placeholder="Search by sample, location, or ID..."
              value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
              InputProps={{startAdornment: <InputAdornment position="start"><Search color="action" /></InputAdornment>}}
            />
          </Grid>
          <Grid item xs={12} md={3}>
            <TextField fullWidth select size="small" label="Filter by Status"
              value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
              InputProps={{startAdornment: <InputAdornment position="start"><FilterList color="action" /></InputAdornment>}}
            >
              {['all','completed','failed'].map(s => <MenuItem key={s} value={s}>{s==='all'?'All Results':s.charAt(0).toUpperCase()+s.slice(1)}</MenuItem>)}
            </TextField>
          </Grid>
          <Grid item xs={12} md={3}>
            <Box display="flex" justifyContent="flex-end" gap={2}>
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
              <Grid item xs={12} md={6}>
                <Typography variant="subtitle2" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <CalendarToday fontSize="small" color="primary" />
                  Date Range
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={6}>
                    <TextField fullWidth size="small" type="date" label="From" value={dateFrom}
                      onChange={(e) => setDateFrom(e.target.value)} InputLabelProps={{ shrink: true }} />
                  </Grid>
                  <Grid item xs={6}>
                    <TextField fullWidth size="small" type="date" label="To" value={dateTo}
                      onChange={(e) => setDateTo(e.target.value)} InputLabelProps={{ shrink: true }} />
                  </Grid>
                </Grid>
              </Grid>
              
              <Grid item xs={12} md={6}>
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
              
              <Grid item xs={12} md={6}>
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
              
              <Grid item xs={12} md={6}>
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
              
              <Grid item xs={12} md={6}>
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
              
              <Grid item xs={12}>
                <Box display="flex" justifyContent="flex-end" gap={2}>
                  <Button variant="outlined" onClick={handleClearFilters} size="small">Clear Filters</Button>
                  <Button variant="contained" onClick={loadRuns} size="small" startIcon={<FilterList />}>Apply Filters</Button>
                </Box>
              </Grid>
            </Grid>
          </AccordionDetails>
        </Accordion>
      </Paper>

      <TableContainer component={Paper} elevation={3}>
        <Table>
          <TableHead>
            <TableRow sx={{ backgroundColor: 'primary.main' }}>
              {['ID','Sample','Platform','Location','Status','Started','Duration','Actions'].map(h => 
                <TableCell key={h} sx={{ color: 'white', fontWeight: 'bold' }} align={h==='Actions'?'center':'left'}>{h}</TableCell>
              )}
            </TableRow>
          </TableHead>
          <TableBody>
            {paginatedRuns.length === 0 ? (
              <TableRow><TableCell colSpan={8} align="center">
                <Box sx={{ py: 6 }}>
                  <Assessment sx={{ fontSize: 60, color: 'text.secondary', mb: 2 }} />
                  <Typography variant="h6" color="text.secondary">No Pipeline Runs Found</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {searchQuery||statusFilter!=='all'?'Try adjusting filters':'Execute a pipeline to see results'}
                  </Typography>
                </Box>
              </TableCell></TableRow>
            ) : paginatedRuns.map((r) => (
              <TableRow key={r.pipeline_id} hover sx={{'&:hover':{backgroundColor:'action.hover'},cursor:'pointer'}} onClick={()=>navigate(`/results/${r.sample_code||r.pipeline_id}`)}>
                <TableCell><Typography variant="body2" fontWeight="medium" color="primary">#{r.pipeline_id}</Typography></TableCell>
                <TableCell>
                  <Box>
                    <Typography variant="body2" fontWeight="medium">{r.sample_code||'Unknown'}</Typography>
                    {r.sample_type && <Chip label={r.sample_type} size="small" variant="outlined" sx={{mt:0.5,height:20,fontSize:'0.7rem'}} />}
                  </Box>
                </TableCell>
                <TableCell><Chip icon={<Science/>} label={r.sequencing_platform||'Oxford Nanopore'} size="small" color="primary" variant="outlined" /></TableCell>
                <TableCell>
                  {r.location?.name ? (
                    <Box display="flex" alignItems="center">
                      <Place fontSize="small" sx={{mr:0.5,color:'text.secondary'}} />
                      <Tooltip title={`${r.location.city||''} ${r.location.country||''}`.trim()||r.location.name}>
                        <Typography variant="body2" noWrap sx={{maxWidth:150}}>{r.location.name}</Typography>
                      </Tooltip>
                    </Box>
                  ) : <Typography variant="body2" color="text.secondary">N/A</Typography>}
                </TableCell>
                <TableCell><Chip icon={getStatusIcon(r.status)} label={r.status||'unknown'} color={getStatusColor(r.status)} size="small" sx={{minWidth:110,fontWeight:'medium'}} /></TableCell>
                <TableCell>
                  <Box display="flex" alignItems="center">
                    <CalendarToday fontSize="small" sx={{mr:0.5,color:'text.secondary'}} />
                    <Typography variant="body2">{formatDate(r.started_at)}</Typography>
                  </Box>
                </TableCell>
                <TableCell><Typography variant="body2" fontWeight="medium">{r.runtime_minutes?`${r.runtime_minutes} min`:r.status==='running'?'⏱ Running...':'N/A'}</Typography></TableCell>
                <TableCell align="center" onClick={(e)=>e.stopPropagation()}>
                  <Tooltip title="View Detailed Results"><IconButton size="small" color="primary" onClick={()=>navigate(`/results/${r.sample_code||r.pipeline_id}`)}><Visibility/></IconButton></Tooltip>
                  <Tooltip title="Monitor Pipeline"><IconButton size="small" color="info" onClick={()=>navigate(`/pipeline/${r.pipeline_id}/monitor`)}><Assessment/></IconButton></Tooltip>
                  {r.results_path && <Tooltip title="Download Results"><IconButton size="small" color="secondary" onClick={()=>window.open(`${API_BASE_URL}/api/pipeline/runs/${r.pipeline_id}/download`,'_blank')}><Download/></IconButton></Tooltip>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <TablePagination rowsPerPageOptions={[10, 25, 50, 100]} component="div" count={filteredRuns.length} rowsPerPage={rowsPerPage} page={page} 
          onPageChange={(e,p)=>setPage(p)} onRowsPerPageChange={(e)=>{setRowsPerPage(+e.target.value);setPage(0);}} />
      </TableContainer>
    </Container>
  );
}

export default ResultsViewer;
