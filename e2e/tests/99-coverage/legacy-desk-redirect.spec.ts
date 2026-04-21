import { createLegacyRedirectSpec } from '@lifegence/e2e-common';

createLegacyRedirectSpec({
  paths: [
    { legacy: '/app/crm', canonical: '/desk/crm' },
    { legacy: '/app/deal', canonical: '/desk/deal' },
    { legacy: '/app/activity', canonical: '/desk/activity' },
  ],
});
