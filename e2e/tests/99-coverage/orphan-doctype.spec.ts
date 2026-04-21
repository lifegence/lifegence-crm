import * as path from 'path';
import { createOrphanDocTypeSpec } from '@lifegence/e2e-common';
import { KNOWN_UI_HIDDEN_DOCTYPES } from '../../fixtures/coverage-allowlist';

createOrphanDocTypeSpec({
  modules: ['Sales CRM'],
  appRoot: path.resolve(__dirname, '../../../lifegence_crm'),
  entryPoints: ['/desk', '/desk/crm'],
  allowlist: KNOWN_UI_HIDDEN_DOCTYPES,
});
