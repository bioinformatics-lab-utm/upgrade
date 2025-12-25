// AMR Resistance Genes Heatmap
// Displays Abricate results as interactive heatmap

import React, { useState, useEffect } from 'react';
import { Box, Paper, Typography, CircularProgress, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Chip } from '@mui/material';
import axios from 'axios';

function AMRHeatmap({ runId, abricateFile }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (abricateFile) {
      loadAMRData();
    }
  }, [runId, abricateFile]);

  const loadAMRData = async () => {
    try {
      const response = await axios.get(
        `${API.API_BASE_URL}/api/pipeline/results/${runId}/view?path=${encodeURIComponent(abricateFile)}`,
        { responseType: 'text' }
      );
      
      const lines = response.data.split('\n').filter(line => line.trim() && !line.startsWith('#'));
      const parsed = lines.map(line => {
        const parts = line.split('\t');
        return {
          file: parts[0],
          sequence: parts[1],
          start: parts[2],
          end: parts[3],
          strand: parts[4],
          gene: parts[5],
          coverage: parseFloat(parts[6]),
          identity: parseFloat(parts[7]),
          database: parts[8],
          accession: parts[9],
          product: parts[10],
          resistance: parts[11]
        };
      });

      setData(parsed);
      setLoading(false);
    } catch (err) {
      console.error('Error loading AMR data:', err);
      setLoading(false);
    }
  };

  const getIdentityColor = (identity) => {
    if (identity >= 99) return 'success';
    if (identity >= 95) return 'primary';
    if (identity >= 90) return 'warning';
    return 'error';
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={3}>
        <CircularProgress />
      </Box>
    );
  }

  if (data.length === 0) {
    return (
      <Paper elevation={2} sx={{ p: 2 }}>
        <Typography variant="body1" color="text.secondary">
          No AMR genes detected
        </Typography>
      </Paper>
    );
  }

  return (
    <Paper elevation={2} sx={{ p: 2 }}>
      <Typography variant="h6" gutterBottom>
        AMR Genes Detected (Abricate)
      </Typography>
      <Typography variant="body2" color="text.secondary" gutterBottom>
        {data.length} resistance genes found
      </Typography>
      
      <TableContainer sx={{ maxHeight: 500 }}>
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              <TableCell><strong>Gene</strong></TableCell>
              <TableCell><strong>Resistance</strong></TableCell>
              <TableCell><strong>Identity %</strong></TableCell>
              <TableCell><strong>Coverage %</strong></TableCell>
              <TableCell><strong>Database</strong></TableCell>
              <TableCell><strong>Product</strong></TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.map((row, idx) => (
              <TableRow key={idx} hover>
                <TableCell>
                  <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                    {row.gene}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip 
                    label={row.resistance || 'Unknown'} 
                    size="small" 
                    color="error"
                  />
                </TableCell>
                <TableCell>
                  <Chip 
                    label={`${row.identity.toFixed(1)}%`}
                    size="small"
                    color={getIdentityColor(row.identity)}
                  />
                </TableCell>
                <TableCell>{row.coverage.toFixed(1)}%</TableCell>
                <TableCell>
                  <Chip 
                    label={row.database} 
                    size="small" 
                    variant="outlined"
                  />
                </TableCell>
                <TableCell>
                  <Typography variant="caption" color="text.secondary">
                    {row.product}
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
}

export default AMRHeatmap;
