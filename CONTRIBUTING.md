# Contributing to Product UGC Pipeline v2

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## 🚀 Getting Started

### Prerequisites

- Python 3.8 or higher
- Git
- API keys for LaoZhang and LK888 (for full pipeline testing)

### Setup Development Environment

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/product-ugc-pipeline.git
cd product-ugc-pipeline

# Create feature branch
git checkout -b feature/your-feature-name

# Install dependencies (if requirements.txt exists)
pip install -r requirements.txt
```

## 📝 How to Contribute

### Reporting Bugs

Open an issue with:
- Clear description of the bug
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version)
- Relevant logs/screenshots

### Suggesting Features

Open an issue with:
- Use case description
- Proposed solution
- Alternative solutions considered
- Impact on existing features

### Pull Requests

1. **Fork the repository**
2. **Create a feature branch** from `v2-five-categories`
3. **Make your changes**
   - Follow existing code style
   - Add tests if applicable
   - Update documentation
4. **Commit with clear messages**
   - Use conventional commits: `feat:`, `fix:`, `docs:`, etc.
   - Example: `feat: add support for cosmetics category`
5. **Push to your fork**
6. **Open a Pull Request**

## 🏗️ Project Structure

### Adding a New Category

To add a new product category (e.g., cosmetics):

1. **Create category spec**: `references/category-cosmetics.md`
   - Define inspection dimensions
   - Detail actions table
   - Character Sheet view count
   - Negative prompts

2. **Update classifier**: `scripts/classify_product_category.py`
   - Add keywords to `classify_by_keywords()`
   - Add image features to `classify_by_image_features()`

3. **Add test cases**: `tests/`
   - Create sample product in test suite
   - Add to `create_test_cases.py`

4. **Update documentation**
   - Add to README.md category table
   - Update SKILL.md

5. **Test classification**
   ```bash
   python scripts/classify_product_category.py tests/your-test --force
   ```

### Code Style

- Follow PEP 8 for Python code
- Use type hints where applicable
- Add docstrings to functions
- Keep functions focused and small

Example:
```python
def classify_product(product_folder: Path, force: bool = False) -> dict:
    """
    Classify a product into one of 5 categories.
    
    Args:
        product_folder: Path to product folder with manifest
        force: Force re-classification even if exists
    
    Returns:
        dict with category, confidence, detected_from, product_name
    
    Raises:
        FileNotFoundError: If product_manifest.json missing
    """
    # Implementation...
```

## 🧪 Testing

### Running Tests

```bash
# Classification test
python scripts/classify_product_category.py tests/five-products

# Create new test cases
python scripts/create_test_cases.py tests/my-test

# Full pipeline test (requires API keys)
bash run_pipeline.sh tests/five-products/01-black-tshirt
```

### Adding Tests

When adding new features:
1. Add test cases to `tests/`
2. Document expected output
3. Update test suite README

## 📚 Documentation

### Documentation Structure

```
docs/
├── API.md          # API reference
├── FAQ.md          # Common questions
├── TUTORIAL.md     # Step-by-step guides
└── CATEGORIES.md   # Category specifications
```

### Writing Documentation

- Use clear, concise language
- Include code examples
- Add screenshots where helpful
- Keep documentation in sync with code

## 🤝 Community Guidelines

### Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Assume good intentions

### Communication

- Use GitHub Issues for bugs/features
- Use Discussions for questions
- Tag issues appropriately
- Respond to feedback promptly

## 🎯 Priority Areas

We especially welcome contributions in:

1. **Core Scripts Implementation**
   - `generate_product_identity_lock.py`
   - `generate_usage_pose_sheet.py`
   - `qc_dual_consistency.py`

2. **New Categories**
   - Sports equipment
   - Cosmetics
   - Food products
   - Toys (beyond blocks)

3. **Quality Improvements**
   - Better classification accuracy
   - More robust QC checks
   - Performance optimization

4. **Documentation**
   - Tutorial videos
   - Multi-language support
   - API examples

## 📄 License

By contributing, you agree that your contributions will be licensed under the MIT License.

## ❓ Questions?

- Open a Discussion: https://github.com/peipeijiang/product-ugc-pipeline/discussions
- Check FAQ: [docs/FAQ.md](docs/FAQ.md)

Thank you for contributing! 🎉

