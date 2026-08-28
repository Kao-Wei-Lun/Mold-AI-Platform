<script setup lang="ts">
import { computed, useId } from "vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

const props = withDefaults(
  defineProps<{
    label: string;
    required?: boolean;
    helper?: string;
    error?: string;
  }>(),
  { required: false, helper: "", error: "" },
);

const generatedId = useId();
const fieldId = `field-${generatedId}`;
const helperId = `${fieldId}-helper`;
const errorId = `${fieldId}-error`;
const describedBy = computed(() =>
  [props.helper ? helperId : "", props.error ? errorId : ""].filter(Boolean).join(" ") || undefined,
);
</script>

<template>
  <label class="form-field" :class="{ 'form-field-invalid': Boolean(error) }">
    <span class="form-field-label">
      {{ label }}
      <abbr v-if="required" class="required-mark" :title="t('Required')" aria-hidden="true">*</abbr>
      <span v-if="required" class="visually-hidden"> ({{ t("Required") }})</span>
    </span>
    <slot
      :field-id="fieldId"
      :described-by="describedBy"
      :invalid="Boolean(error)"
    />
    <small v-if="helper" :id="helperId" class="field-hint">{{ helper }}</small>
    <small v-if="error" :id="errorId" class="field-error" role="alert">{{ error }}</small>
  </label>
</template>
