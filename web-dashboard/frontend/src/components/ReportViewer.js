// Interactive bioinformatics report viewer for HTML reports
// Displays NanoPlot, QUAST, Nextflow, and other HTML reports in an iframe

import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  IconButton,
  Toolbar,
  AppBar,
  Tooltip,
  CircularProgress,
  Alert
} from '@mui/material';
import {
  Close as CloseIcon,
  GetApp as DownloadIcon,
  OpenInNew as OpenInNewIcon,
  Refresh as RefreshIcon
} from '@mui/icons-material';
import API from '../config/api';

function ReportViewer({ runId, filePath, fileName, onClose }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const API_BASE_URL = API.API_BASE_URL;
  const viewUrl = `${API_BASE_URL}/api/pipeline/results/${runId}/view?path=${encodeURIComponent(filePath)}`;
  const downloadUrl = `${API_BASE_URL}/api/pipeline/results/${runId}/download?path=${encodeURIComponent(filePath)}`;

  const handleLoad = () => {
    setLoading(false);
  };

  const handleError = () => {
    setLoading(false);
    setError('Failed to load report');
  };

  const handleDownload = () => {
    window.open(downloadUrl, '_blank');
  };

  const handleOpenNew = () => {
    window.open(viewUrl, '_blank');
  };

  const handleRefresh = () => {
    setLoading(true);
    setError(null);
    // Force iframe reload by changing key
    const iframe = document.getElementById('report-iframe');
    if (iframe) {
      iframe.src = iframe.src;
    }
  };

  return (
    <Paper 
      elevation={3} 
      sx={{ 
        position: 'fixed',
        top: 80,
        left: 20,
        right: 20,
        bottom: 20,
        zIndex: 1300,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden'
      }}
    >
      <AppBar position="static" color="default" elevation={1}>
        <Toolbar variant="dense">
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            {fileName}
          </Typography>
          
          <Tooltip title="Refresh">
            <IconButton onClick={handleRefresh} size="small">
              <RefreshIcon />
            </IconButton>
          </Tooltip>
          
          <Tooltip title="Open in New Tab">
            <IconButton onClick={handleOpenNew} size="small">
              <OpenInNewIcon />
            </IconButton>
          </Tooltip>
          
          <Tooltip title="Download">
            <IconButton onClick={handleDownload} size="small">
              <DownloadIcon />
            </IconButton>
          </Tooltip>
          
          <Tooltip title="Close">
            <IconButton onClick={onClose} size="small">
              <CloseIcon />
            </IconButton>
          </Tooltip>
        </Toolbar>
      </AppBar>

      <Box sx={{ flexGrow: 1, position: 'relative', overflow: 'hidden' }}>
        {loading && (
          <Box 
            display="flex" 
            justifyContent="center" 
            alignItems="center" 
            height="100%"
          >
            <CircularProgress />
          </Box>
        )}
        
        {error && (
          <Box p={3}>
            <Alert severity="error">{error}</Alert>
          </Box>
        )}
        
        <iframe
          id="report-iframe"
          src={viewUrl}
          title={fileName}
          style={{
            width: '100%',
            height: '100%',
            border: 'none',
            display: loading ? 'none' : 'block'
          }}
          onLoad={handleLoad}
          onError={handleError}
        />
      </Box>
    </Paper>
  );
}

export default ReportViewer;
