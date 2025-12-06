import { ScoreConfig, defaultScoreConfig, ruleCategoryMap, fileTypePatterns } from './scoreConfig';

export interface Finding {
  id: string;
  rule: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  message: string;
  file: string;
  locations: any[];
  fixable?: boolean; // Whether this finding can be auto-fixed
}

export interface ScoreResult {
  overall: number;
  breakdown: {
    totalFindings: number;
    severityBreakdown: { [key: string]: number };
    categoryBreakdown: { [key: string]: number };
    fileTypeBreakdown: { [key: string]: number };
    concentrationPenalty: number;
    volumePenalty: number;
    totalDeductions: number;
    categoryImpacts: { [key: string]: number }; // New: asymptotic impacts per category
  };
  subScores: {
    complexity: number | null;
    coverage: number | null;
    documentation: number | null;
  };
  insights: string[];
  potentialImprovement?: number; // Points that could be gained by auto-fixing
}

export class AsymptoticScoreEngine {
  private config: ScoreConfig;

  constructor(config: ScoreConfig = defaultScoreConfig) {
    this.config = config;
  }

  /**
   * Calculate the overall code quality score using asymptotic formula
   * Formula: For each category: 
   * - Calculate 0-100 scale impact using asymptotic formula
   * - Multiply by category weight percentage  
   * - Subtract from base score
   */
  calculateScore(findings: Finding[]): ScoreResult {
    const breakdown = this.calculateAsymptoticBreakdown(findings);
    const subScores = this.calculateSubScores(findings);
    const insights = this.generateInsights(findings, breakdown);

    // Start with perfect score (100)
    let overall = 100;
    
    // Apply asymptotic damage deductions for each category
    // categoryImpact already represents asymptotic damage (0-100 scale)
    // where each additional finding contributes less damage (diminishing returns)
    for (const [category, categoryWeight] of Object.entries(this.config.categoryWeights)) {
      const categoryImpact = breakdown.categoryImpacts[category] || 0;
      // Apply weighted damage: asymptotic impact * category weight
      const weightedDamage = categoryImpact * (categoryWeight / 100);
      overall -= weightedDamage;
    }
    
    // Apply additional penalties (concentration and volume)
    overall -= breakdown.concentrationPenalty;
    overall -= breakdown.volumePenalty;
    
    // Ensure score doesn't go below 0 (but CAN reach 0 with enough violations)
    overall = Math.max(0, overall);

    // Calculate potential improvement if auto-fixable issues were fixed
    const fixableFindings = findings.filter(f => f.fixable);
    let potentialImprovement = 0;
    
    if (fixableFindings.length > 0) {
      // Calculate score without fixable findings
      const nonFixableFindings = findings.filter(f => !f.fixable);
      
      const improvedBreakdown = this.calculateAsymptoticBreakdown(nonFixableFindings);
      
      let improvedScore = 100;
      for (const [category, categoryWeight] of Object.entries(this.config.categoryWeights)) {
        const categoryImpact = improvedBreakdown.categoryImpacts[category] || 0;
        const weightedDamage = categoryImpact * (categoryWeight / 100);
        improvedScore -= weightedDamage;
      }
      
      improvedScore -= improvedBreakdown.concentrationPenalty;
      improvedScore -= improvedBreakdown.volumePenalty;
      improvedScore = Math.max(0, improvedScore);
      
      potentialImprovement = Math.round((improvedScore - overall) * 10) / 10;
    }

    return {
      overall: Math.round(overall * 10) / 10,
      breakdown,
      subScores,
      insights,
      potentialImprovement
    };
  }

  /**
   * Calculate asymptotic breakdown using exponential decay formula
   * Each category gets a 0-100 scale impact based on findings severity/amount
   */
  private calculateAsymptoticBreakdown(findings: Finding[]) {
    const severityBreakdown: { [key: string]: number } = {};
    const fileTypeBreakdown: { [key: string]: number } = {};
    const categoryImpacts: { [key: string]: number } = {};
    
    // Group findings by category
    const categoryFindings: { [key: string]: Finding[] } = {};
    
    const fileConcentration: { [file: string]: number } = {};

    // Process each finding and group by category
    for (const finding of findings) {
      // Track severity breakdown (count of findings per severity)
      severityBreakdown[finding.severity] = (severityBreakdown[finding.severity] || 0) + 1;
      
      // Track file type breakdown (count of findings per file type)
      const fileType = this.getFileType(finding.file);
      fileTypeBreakdown[fileType] = (fileTypeBreakdown[fileType] || 0) + 1;
      
      // Group by category
      const category = this.getCategoryForRule(finding.rule);
      if (!categoryFindings[category]) {
        categoryFindings[category] = [];
      }
      categoryFindings[category].push(finding);
      
      // Track file concentration
      fileConcentration[finding.file] = (fileConcentration[finding.file] || 0) + 1;
    }

    // Initialize all categories with 0 impact
    for (const category of Object.keys(this.config.categoryWeights)) {
      categoryImpacts[category] = 0;
    }

    // Calculate asymptotic impact for each category that has findings
    for (const [category, categoryFindingList] of Object.entries(categoryFindings)) {
      // Use default asymptotic parameters if category not configured
      let maxImpact = 100; // Default to full 100 scale
      let steepness = 0.3;  // Default steepness
      
      if (this.config.asymptoteFunctions[category]) {
        const asymptoteParams = this.config.asymptoteFunctions[category];
        // Convert maxImpact from config to 0-100 scale 
        // (config values are weighted points, we need 0-100 scale)
        maxImpact = 100; // Always use full 100 scale, weight applied later
        steepness = asymptoteParams.steepness;
      }

      // Calculate weighted findings count for this category
      let weightedFindings = 0;
      for (const finding of categoryFindingList) {
        const severityWeight = this.config.severityWeights[finding.severity] || 1.0;
        const fileTypeWeight = this.getFileTypeWeight(finding.file);
        weightedFindings += severityWeight * fileTypeWeight;
      }

      // Apply asymptotic formula: impact = maxImpact * (1 - e^(-steepness * weightedFindings))
      // This gives us a 0-100 scale impact for this category
      const rawImpact = maxImpact * (1 - Math.exp(-steepness * weightedFindings));
      
      categoryImpacts[category] = Math.min(100, rawImpact); // Cap at 100
    }

    // Calculate traditional category breakdown for compatibility (showing actual deductions)
    const categoryBreakdown: { [key: string]: number } = {};
    for (const [category, impact] of Object.entries(categoryImpacts)) {
      const categoryWeight = (this.config.categoryWeights as any)[category] || 0;
      categoryBreakdown[category] = impact * (categoryWeight / 100);
    }

    // Calculate penalties
    const totalDeductions = Object.values(categoryBreakdown).reduce((a, b) => a + b, 0);
    const concentrationPenalty = this.calculateConcentrationPenalty(fileConcentration, totalDeductions);
    const volumePenalty = this.calculateVolumePenalty(findings.length, totalDeductions);

    return {
      totalFindings: findings.length,
      severityBreakdown,
      categoryBreakdown,
      fileTypeBreakdown,
      concentrationPenalty,
      volumePenalty,
      totalDeductions: totalDeductions + concentrationPenalty + volumePenalty,
      categoryImpacts
    };
  }

  /**
   * Get file type weight multiplier
   */
  private getFileTypeWeight(filePath: string): number {
    const fileType = this.getFileType(filePath);
    return this.config.fileTypeWeights[fileType] || 1.0;
  }

  /**
   * Calculate concentration penalty when findings cluster in few files
   * Returns a small fixed penalty (not multiplied to avoid double-penalization)
   */
  private calculateConcentrationPenalty(fileConcentration: { [file: string]: number }, baseDeductions: number): number {
    if (!this.config.concentrationPenalty.enabled) return 0;
    
    const problemFiles = Object.values(fileConcentration)
      .filter(count => count > this.config.concentrationPenalty.threshold);
    
    if (problemFiles.length === 0) return 0;
    
    // Small fixed penalty per problem file to avoid double-penalization
    return Math.min(10, problemFiles.length * 2); // Max 10 point penalty for concentration
  }

  /**
   * Calculate volume penalty for high number of findings
   * Returns a fixed-point penalty (not multiplied by baseDeductions to avoid double-penalization)
   */
  private calculateVolumePenalty(findingCount: number, baseDeductions: number): number {
    // Volume penalties should be small fixed amounts, not multipliers on top of category damage
    // Otherwise we double-penalize: once for the findings themselves, again for the count
    
    const thresholds = this.config.volumePenalties.thresholds;
    
    // Return small fixed penalties based on volume tiers
    if (findingCount <= thresholds[0]) return 0;           // 0-25 findings: no penalty
    if (findingCount <= thresholds[1]) return 1;           // 26-75: -1 point
    if (findingCount <= thresholds[2]) return 2;           // 76-150: -2 points
    if (findingCount <= thresholds[3]) return 4;           // 151-300: -4 points
    if (findingCount <= thresholds[4]) return 6;           // 301-500: -6 points
    return 8;                                              // 500+: -8 points
  }

  /**
   * Calculate sub-scores for detailed analysis
   */
  private calculateSubScores(findings: Finding[]) {
    const result: any = {
      complexity: null,
      coverage: null,
      documentation: null
    };

    if (this.config.subScores.complexity.enabled) {
      result.complexity = this.calculateComplexityScore(findings);
    }

    if (this.config.subScores.coverage.enabled) {
      result.coverage = this.calculateCoverageScore(findings);
    }

    if (this.config.subScores.documentation.enabled) {
      result.documentation = this.calculateDocumentationScore(findings);
    }

    return result;
  }

  /**
   * Calculate complexity sub-score with asymptotic considerations
   */
  private calculateComplexityScore(findings: Finding[]): number {
    const complexityFindings = findings.filter(f => 
      this.getCategoryForRule(f.rule) === 'complexity');
    
    const criticalComplexity = complexityFindings.filter(f => 
      f.severity === 'critical' || f.severity === 'high').length;
    
    // Use asymptotic formula for complexity scoring
    const params = this.config.asymptoteFunctions.complexity;
    if (params) {
      const impact = params.maxImpact * (1 - Math.exp(-params.steepness * complexityFindings.length));
      return Math.round((100 - impact) * 10) / 10;
    }
    
    // Fallback calculation
    let complexityScore = 100;
    complexityScore -= criticalComplexity * 8;
    complexityScore -= (complexityFindings.length - criticalComplexity) * 1.5;
    complexityScore = Math.max(20, complexityScore);
    
    return Math.round(complexityScore * 10) / 10;
  }

  /**
   * Calculate coverage sub-score
   */
  private calculateCoverageScore(findings: Finding[]): number {
    const allFiles = [...new Set(findings.map(f => f.file))];
    const testFiles = allFiles.filter(file => this.getFileType(file) === 'test').length;
    const sourceFiles = allFiles.filter(file => this.getFileType(file) === 'core').length;
    
    const testRatio = sourceFiles > 0 ? testFiles / sourceFiles : 0;
    const expectedRatio = this.config.subScores.coverage.testFileRatio;
    
    const coverageScore = Math.min(100, (testRatio / expectedRatio) * 100);
    
    return Math.round(coverageScore * 10) / 10;
  }

  /**
   * Calculate documentation sub-score
   * Note: No documentation rules in alpha_default, so this returns 100 (perfect)
   * unless TODO/comment style rules are present
   */
  private calculateDocumentationScore(findings: Finding[]): number {
    // Count style findings that are documentation-related (TODOs, comments)
    const docRelatedFindings = findings.filter(f => {
      const rule = f.rule.toLowerCase();
      return rule.includes('todo') || rule.includes('comment') || rule.includes('doc');
    });
    
    if (docRelatedFindings.length === 0) {
      return 100; // Perfect score if no doc-related issues
    }
    
    // Simple scoring: start at 100, reduce based on doc findings
    let docScore = 100;
    docScore -= docRelatedFindings.length * 2;
    docScore = Math.max(30, docScore);
    
    return Math.round(docScore * 10) / 10;
  }

  /**
   * Get category for a rule name
   */
  private getCategoryForRule(rule: string): keyof ScoreConfig['categoryWeights'] {
    const ruleLower = rule.toLowerCase();
    
    for (const [pattern, category] of Object.entries(ruleCategoryMap)) {
      if (ruleLower.includes(pattern)) {
        return category;
      }
    }
    
    return 'style'; // Default category (lowest impact for unknown rules)
  }

  /**
   * Determine file type from file path
   */
  private getFileType(filePath: string): keyof ScoreConfig['fileTypeWeights'] {
    for (const [type, patterns] of Object.entries(fileTypePatterns)) {
      if (patterns.some(pattern => pattern.test(filePath))) {
        return type as keyof ScoreConfig['fileTypeWeights'];
      }
    }
    
    return 'other';
  }

  /**
   * Generate insights about the score with asymptotic considerations
   */
  private generateInsights(findings: Finding[], breakdown: any): string[] {
    const insights: string[] = [];
    
    // Severity insights
    const criticalCount = findings.filter(f => f.severity === 'critical').length;
    const highCount = findings.filter(f => f.severity === 'high').length;
    
    if (criticalCount > 10) {
      insights.push(`${criticalCount} critical issues require immediate attention`);
    } else if (criticalCount > 0) {
      insights.push(`${criticalCount} critical issue${criticalCount > 1 ? 's' : ''} need${criticalCount === 1 ? 's' : ''} fixing`);
    }
    
    if (highCount > 15) {
      insights.push(`High number of high-severity issues (${highCount}) significantly impact quality`);
    } else if (highCount > 5) {
      insights.push(`${highCount} high-severity issues should be prioritized`);
    }
    
    // Category insights with asymptotic awareness
    const topCategory = Object.entries(breakdown.categoryImpacts || {})
      .sort(([,a], [,b]) => (b as number) - (a as number))[0];
    
    if (topCategory && (topCategory[1] as number) > 5) {
      insights.push(`${topCategory[0]} issues are the main quality concern (${Math.round(topCategory[1] as number)} point impact)`);
    }
    
    // Asymptotic insights - Updated for new categories
    const securityImpact = breakdown.categoryImpacts?.security || 0;
    const architectureImpact = breakdown.categoryImpacts?.architecture || 0;
    const reliabilityImpact = breakdown.categoryImpacts?.reliability || 0;
    
    if (securityImpact > 15) {
      insights.push(`Security impact approaching maximum (${Math.round(securityImpact)}/25 points) - prioritize existing security issues`);
    }
    
    if (architectureImpact > 10) {
      insights.push(`Architecture impact significant (${Math.round(architectureImpact)}/15 points) - Tier 2 analysis detected structural issues`);
    }
    
    if (reliabilityImpact > 10) {
      insights.push(`Reliability impact significant (${Math.round(reliabilityImpact)}/15 points) - focus on bug prevention`);
    }
    
    // Volume insights
    if (findings.length > 200) {
      insights.push(`Very high volume of findings (${findings.length}) indicates systemic issues`);
    } else if (findings.length > 75) {
      insights.push(`High volume of findings (${findings.length}) suggests systematic problems`);
    }
    
    // Concentration insights
    if (breakdown.concentrationPenalty > 3) {
      insights.push(`Issues concentrated in few files - consider targeted refactoring`);
    }
    
    // Positive insights
    if (findings.length === 0) {
      insights.push(`Excellent! No issues found - exemplary code quality`);
    } else if (findings.length < 10 && criticalCount === 0) {
      insights.push(`Very good code quality with minimal issues`);
    } else if (findings.length < 25 && criticalCount === 0) {
      insights.push(`Good code quality with minor improvements needed`);
    }
    
    const totalImpact = Object.values(breakdown.categoryImpacts || {}).reduce((a, b) => (a as number) + (b as number), 0) as number;
    if (totalImpact < 10 && criticalCount === 0) {
      insights.push(`Strong foundation with only minor quality concerns`);
    }
    
    // Production readiness insights
    if (criticalCount === 0 && highCount < 5) {
      insights.push(`Production-ready with standard quality practices`);
    }
    
    return insights;
  }

  /**
   * Update scoring configuration
   */
  updateConfig(newConfig: Partial<ScoreConfig>): void {
    this.config = { ...this.config, ...newConfig };
  }

  /**
   * Get current configuration
   */
  getConfig(): ScoreConfig {
    return { ...this.config };
  }
}

// Export AsymptoticScoreEngine as ScoreEngine for compatibility
export { AsymptoticScoreEngine as ScoreEngine };