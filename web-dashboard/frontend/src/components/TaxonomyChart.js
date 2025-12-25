// Kraken2/Bracken Taxonomy Visualization
// Sunburst chart for taxonomic distribution

import React, { useState, useEffect } from 'react';
import { Box, Paper, Typography, CircularProgress } from '@mui/material';
import Plot from 'react-plotly.js';
import axios from 'axios';
import API from '../config/api';
import logger from '../utils/logger';

function TaxonomyChart({ runId, krakenFile }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (krakenFile) {
      loadTaxonomyData();
    }
  }, [runId, krakenFile]);

  const loadTaxonomyData = async () => {
    try {
      // Parse Kraken report format
      const response = await axios.get(
        `${API.API_BASE_URL}/api/pipeline/results/${runId}/view?path=${encodeURIComponent(krakenFile)}`,
        { responseType: 'text' }
      );
      
      const lines = response.data.split('\n').filter(line => line.trim());
      const parsed = lines.map(line => {
        const parts = line.trim().split('\t');
        return {
          percentage: parseFloat(parts[0]),
          reads_clade: parseInt(parts[1]),
          reads_taxon: parseInt(parts[2]),
          rank: parts[3],
          taxid: parts[4],
          name: parts[5]?.trim()
        };
      });

      // Build sunburst data
      const labels = ['All'];
      const parents = [''];
      const values = [100];
      const colors = [];

      parsed.forEach(item => {
        if (item.percentage > 0.1) { // Filter small values
          labels.push(item.name);
          parents.push(item.rank === 'D' ? 'All' : 'All'); // Simplified hierarchy
          values.push(item.percentage);
          
          // Color by rank
          const rankColors = {
            'D': '#1f77b4', // Domain
            'P': '#ff7f0e', // Phylum
            'C': '#2ca02c', // Class
            'O': '#d62728', // Order
            'F': '#9467bd', // Family
            'G': '#8c564b', // Genus
            'S': '#e377c2'  // Species
          };
          colors.push(rankColors[item.rank] || '#7f7f7f');
        }
      });

      setData({ labels, parents, values, colors });
      setLoading(false);
    } catch (err) {
      console.error('Error loading taxonomy data:', err);
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={3}>
        <CircularProgress />
      </Box>
    );
  }

  if (!data) return null;

  return (
    <Paper elevation={2} sx={{ p: 2 }}>
      <Typography variant="h6" gutterBottom>
        Taxonomic Distribution (Kraken2)
      </Typography>
      <Plot
        data={[
          {
            type: 'sunburst',
            labels: data.labels,
            parents: data.parents,
            values: data.values,
            marker: { colors: data.colors },
            hovertemplate: '<b>%{label}</b><br>%{value:.2f}%<extra></extra>',
            textfont: { size: 12 }
          }
        ]}
        layout={{
          width: 600,
          height: 600,
          margin: { l: 0, r: 0, b: 0, t: 40 },
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(0,0,0,0)'
        }}
        config={{ responsive: true }}
      />
    </Paper>
  );
}

export default TaxonomyChart;
