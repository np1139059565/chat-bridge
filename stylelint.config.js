module.exports = {
  extends: ['stylelint-config-standard'],
  rules: {
    // 项目 CSS 历史格式多样，放宽风格类规则，只保留正确性检查
    'color-hex-length': null,
    'color-function-notation': null,
    'alpha-value-notation': null,
    'declaration-block-single-line-max-declarations': null,
    'rule-empty-line-before': null,
    'comment-empty-line-before': null,
    'no-descending-specificity': null,
    'no-duplicate-selectors': null,
    'selector-class-pattern': null,
    'media-feature-range-notation': null,
    'font-family-no-missing-generic-family-keyword': [
      true,
      { ignoreFontFamilies: ['system-ui'] }
    ],
    'declaration-block-no-duplicate-properties': true,
    'no-empty-source': true
  }
};
