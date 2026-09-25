<?php

declare(strict_types=1);

/**
 * Every message in English, which is the list a locale file is filled in
 * against.
 *
 * Patterns are ICU MessageFormat. A locale file needs only the keys it
 * translates, and anything absent is read from here
 */
return [
    'file.is_a_directory' => '{path} is a directory, not a file.',
    'file.unreadable' => 'Could not read {path}.',
    'json.invalid' => '{what} is not valid JSON: {detail}',
    'json.not_an_object' => '{what} should hold a JSON object.',
    'json.report_unencodable' => 'This report cannot be written as JSON: {detail}.',

    'env.not_a_file' => '{path} is not a file this can read variables from.',
    'env.no_such_file' => 'There is no env file at {path}.',
    'env.unreadable' => '{path} cannot be read.',
    'auth.env_default' => 'the environment or in a .env in the working directory',
    'auth.no_key' => 'No {name} in {where}. {rules_alone, select, yes {Set one, or run the rules without asking Jev.} other {Set one.}}',

    'config.not_found' => 'No config at {path}.',
    'config.unknown_setting' => '{path}: there is no "{names}" setting. This file takes "accept" and "jev".',
    'config.accept_not_a_list' => '{path}: "accept" should be a list.',
    'config.entry_not_an_object' => '{path}: entry {entry} should be an object.',
    'config.entry_names_no_check' => '{path}: entry {entry} names no check.',
    'config.acceptance_needs_a_reason' => '{path}: accepting `{check}` needs a reason saying why the finding does not apply here.',
    'config.jev_not_a_version' => '{path}: "jev" should be a version such as "1.13", or "latest".',

    'flags.needs_two_dashes' => 'An option takes two dashes: write {options}.',
    'flags.needs_two_dashes_item' => '`{given}` as `--{fixed}`',
    'flags.repeated' => '{options} {count, plural, one {is} other {are}} given more than once. Give it once, with the value you mean.',
    'flags.too_many_arguments' => '`jevlint {command}` takes {takes, plural, =0 {no arguments} other {one argument}}, so it has nothing to do with {extra}.',
    'flags.unknown_option' => '{count, plural, one {No such option} other {No such options}}: {options}. `jevlint {command}` accepts: {accepts}.',
    'flags.needs_a_value' => '--{option} takes a value. Write --{option}=<value>.',
    'flags.empty_value' => '--{option} was given an empty value. Write --{option}=<value>, or leave it off.',
    'flags.dead_with_static_only' => '--static-only makes no calls, so {options} {count, plural, one {has} other {have}} nothing to do. Drop one of them.',
    'flags.brief_with_json' => '--brief shapes the text report and does nothing with --format=json. Drop one of them.',
    'flags.show_accepted_with_json' => '--show-accepted shapes the text report, and the JSON carries every acceptance with its reason. Drop it.',
    'flags.value_not_allowed' => '--{option}={given} is not one of: {allowed}.',

    'args.switch_takes_no_value' => '--{option} is a switch and takes no value. Write --{option}, or leave it off.',
    'args.not_a_number' => '--{option}={given} is not a number.',
    'args.not_a_whole_number' => '--{option}={given} is not a whole number.',
    'args.not_a_count' => '--{option}={given} is not a count. It has to be at least 1.',
    'args.above_the_most' => '--{option}={given} is more than this runs. The most is {most, number, integer}.',
    'args.not_seconds' => '--{option}={given} is not a number of seconds.',

    'query.is_a_list' => '{source} holds a JSON list. A query is an object with `state` and `questions`.',
    'query.questions_is_a_list' => '{source}: "questions" should be an object keyed by question id, not a list.',
    'query.question_not_an_object' => '{source}: question "{id}" should be an object.',
    'query.state_wrong_type' => '{source}: "state" holds {holds}. It should be text, or an object of fields.',
    'query.state_a_number' => 'a number',
    'query.state_a_boolean' => 'true or false',
    'narrow.nothing_named' => '--{option} was given nothing to narrow to. Name what you want, or leave the option off.',
    'check.no_query_file' => 'Give me a query file to check. See `jevlint help`.',
    'probe.no_query_file' => 'Give me a query file to probe. See `jevlint help`.',
    'query.no_such_question' => '{path} has no question called {ids}.',
    'note.below_the_floor' => '--min={floor}, so {count, plural, one {# finding} other {# findings}} below {floor} {count, plural, one {is} other {are}} counted but not listed.',
    'probe.variant_names_no_question' => 'The rewording "{variant}" names no question in {path}. Its questions are: {ids}.',
    'probe.moved_definition' => "A reading moved when its delta cleared both three times the question's floor and {floor, number, ::.00}.",
    'probe.floor_definition' => 'The larger of the spread measured over the repeats and {noise, number, ::.0000}, the floor this tool uses where a run is too short to measure its own.',

    'catalogue.no_such_check' => 'There is no check called {ids}. `jevlint checks` lists them.',
    'catalogue.check_not_for_version' => '{id} is not one of the checks for Jev {jev}. The catalogue covers {versions}.',
    'catalogue.header' => 'catalogue {version}, written against {model}{withheld, plural, =0 {} one { · # check the catalogue writes for another version left out} other { · # checks the catalogue writes for another version left out}}',
    'self_test.withheld_for_version' => '{ids} {count, plural, one {is} other {are}} not written for Jev {jev}, so this run has nothing to score. `jevlint checks --jev={jev}` lists the ones that are.',
    'self_test.static_has_nothing_to_score' => '{ids} {count, plural, one {is} other {are}} a rule, not a judgement, so there is nothing to score. `jevlint self-test` measures model checks.',
    'self_test.no_examples' => '{ids} {count, plural, one {has} other {have}} no examples in {file}, so nothing scored {count, plural, one {it} other {them}}.',
    'catalogue.no_checks' => 'The catalogue at {path} has no checks.',
    'catalogue.version_wrong_type' => 'The catalogue at {path} writes its version as {type}. A version is a string or a whole number.',
    'catalogue.duplicate_id' => 'The catalogue at {path} holds two checks called "{id}".',
    'catalogue.check_not_an_object' => 'The catalogue at {path} holds {type} where check {position} should be. Every check is an object.',
    'catalogue.rule_nothing' => 'nothing',
    'catalogue.unknown_rule' => 'Check "{id}" names the rule {rule}, which no rule in this implementation raises, so it could never fire.',
    'catalogue.rule_shadowed' => 'Checks "{first}" and "{second}" both name the rule "{rule}" under Jev {jev}. One rule raises one finding, so the second could only shadow the first.',
    'catalogue.key_collision' => 'Checks "{first}" and "{second}" are asked under the same key "{key}" under Jev {jev}, so one answer would be reported as both.',
    'catalogue.model_without_question' => 'Check "{id}" is a model check and carries no `question`, so it could never fire.',
    'catalogue.unknown_primitive' => 'Check "{id}" applies to "{primitive}", which is not a Jev primitive, so it could never fire. The primitives are {primitives}, or `*`.',
    'catalogue.supersedes_unknown' => 'Check "{id}" supersedes "{other}", which is not a check in this catalogue.',
    'catalogue.covers_no_version' => 'Check "{id}" is written for no Jev version this catalogue covers ({versions}), so it can never run.',
    'catalogue.no_versions' => 'The catalogue at {path} does not name the Jev versions it covers. Give it a "jev" list, such as ["1.13"].',
    'catalogue.version_malformed' => 'The catalogue at {path} covers a Jev version written as "{version}". A version is digits and dots, such as 1.13.',
    'catalogue.checks_dir_missing_file' => 'JEVLINT_CHECKS_DIR is {dir}, which holds no {file}.',
    'catalogue.checks_not_found' => 'Could not find checks/{file}. Set JEVLINT_CHECKS_DIR to the directory holding it.',
    'catalogue.not_a_version' => '{from, select, config {{source} pins Jev {requested}, which} other {--jev={requested}}} is not a Jev version. Write it as digits and dots, such as 1.13, or as `latest`.',
    'catalogue.version_not_covered' => '{from, select, config {{source} pins Jev {requested}, which} other {Jev {requested}}} is not a version this catalogue is written for. It covers {versions}.',
    'check.trigger_out_of_range' => 'Check "{id}" has a trigger of {trigger}. A trigger outside 0.3 to 0.95 makes the check fire on everything or on nothing.',
    'check.missing_field' => 'A check is missing its "{field}".',
    'check.bad_severity' => 'Check "{id}" has a severity of "{given}". It has to be one of: {allowed}.',
    'check.bad_mode' => 'Check "{id}" has a mode of "{given}". It has to be one of: {allowed}.',
    'check.model_without_trigger' => 'Check "{id}" is a judgement with no trigger, so it would be gated on a default nobody wrote.',
    'check.bad_scope' => 'Check "{id}" has a scope of "{given}". It has to be one of: {allowed}.',
    'check.applies_to_nothing' => 'Check "{id}" applies to nothing, so it can never fire. Name the primitives it covers, or `*`.',
    'check.empty_version_span' => 'Check "{id}" runs from Jev {since} until Jev {until}, which is no versions at all.',
    'check.bad_version' => 'Check "{id}" has a "{field}" of {given}. A Jev version is written as digits and dots, such as 1.13.',
    'check.bad_suppress_entry' => 'Check "{id}" has a `suppress` entry that is not \'{\'answer, when\'}\'.',
    'check.bad_second_question' => 'Check "{id}" has a `{name}` that is not a Noul `question` with a `trigger` between 0 and 1.',
    'check.unknown_suppression' => 'Check "{id}" suppresses on "{given}", which nothing tests. The conditions are: {allowed}.',
    'check.unknown_reads' => 'Check "{id}" reads "{given}", which is not a part of a query. It is one of: {allowed}.',
    'narrow.withheld_for_version' => '{ids} {count, plural, one {is} other {are}} not written for Jev {jev}. `jevlint checks --jev={jev}` lists the ones that are.',
    'config.accepts_unknown_check' => '{source} accepts {ids}, which the catalogue does not hold.',
    'note.version_covered' => '{source} names {model}, and this run checked it against the rules for Jev {jev}. Check it against its own with Jev {named}.',
    'note.version_not_covered' => '{source} names {model}, and this run checked it against the rules for Jev {jev}. This catalogue holds no rules for {named}.',
    'skipped.questions_left_out' => 'This run carried some of the query, and left {count, plural, one {# question} other {# questions}} in it unchecked.',
    'skipped.jev_not_asked' => 'Jev was not asked, so the {count, plural, one {# check that asks} other {# checks that ask}} it {count, plural, one {was} other {were}} not run.',
    'skipped.state_not_checked' => 'The state was not checked, so the {count, plural, one {# check that reads} other {# checks that read}} it {count, plural, one {was} other {were}} not run.',
    'skipped.narrowed_to' => 'This run carried {count, number, integer} of the {total, number, integer} checks in the catalogue.',
    'skipped.written_for_another_version' => 'Jev {jev}, so the {count, plural, one {# check} other {# checks}} the catalogue writes for another version {count, plural, one {was} other {were}} not run.',

    'self_test.fixture_unknown_check' => '{path} holds a fixture for "{id}", which is not a check in this catalogue.',
    'self_test.fixture_missing_example' => 'The fixture for {id} is missing an example.',
    'report.unreachable' => '{target}: the checks could not be asked - {detail}',
    'report.no_verdict' => '{more, plural, =0 {`{first}`} other {`{first}` and # more}} went into a call and came back with no verdict',
    'probe.question_has_no_type' => 'Question "{id}" has no type this can send.',
    'evidence.found' => 'Found {what}.',
    'evidence.found_quoted' => 'Found "{what}".',
    'evidence.identical_to' => 'Identical to "{other}".',
    'evidence.state_size' => '{size, number, integer} characters, against a {threshold, number, integer} character threshold.',
    'evidence.instructions' => 'Instructions: "{text}".',
    'evidence.keys' => 'Keys: {keys}.',
    'evidence.none' => 'none',
    'evidence.options' => 'Options: {options}.',
    'evidence.reordered_options' => 'Written {written}; a JavaScript caller sends {sent}.',
    'evidence.option_count' => '{count, plural, one {# option} other {# options}}.',
    'evidence.levels' => 'Levels: {levels}.',
    'evidence.level_count' => '{count, plural, one {# level} other {# levels}}.',
    'catalogue.rule_unclaimed' => 'The rule "{rule}" is raised in code but no check in the catalogue claims it.',

    'probe.unsendable_questions' => '{ids} {count, plural, one {has} other {have}} a type this cannot send, so {count, plural, one {it was} other {they were}} not probed. `jevlint check` says what is wrong with {count, plural, one {it} other {them}}.',
    'probe.variant_name_taken' => 'The rewording "{name}" takes the name of a rewrite this already runs. Call it something else; the names in use are {taken}.',
    'probe.variant_not_a_map' => 'The rewording "{name}" should be a map of question id to the rewording, as \'{\'"{name}": \'{\'"question_id": "..."\'}}\'.',
    'probe.variant_not_text' => 'The rewording "{name}" gives question "{id}" a {type}. A rewording is the replacement instructions, as text.',
    'probe.reading_choice' => 'probability of `{label}`',
    'probe.reading_score' => 'position on {levels, number, integer} levels, scaled to 0-1',
    'probe.partial_answer' => 'the call answered {answered, number, integer} of {asked, plural, one {# question} other {# questions}}; `{missing}` did not come back',
    'skipped.unreadable_questions' => '{ids} {count, plural, one {has} other {have}} no type this can read or no instruction to read, so no judgement was asked about {count, plural, one {it} other {them}}.',
    'skipped.state_field_needs_whole_query' => 'This run carried some of the query, so the {count, plural, one {# check} other {# checks}} judging a state field against the whole of it did not run.',
    'skipped.no_state' => 'The query carries no state, so the {count, plural, one {# check that reads} other {# checks that read}} it did not run.',
    'skipped.too_many_questions' => 'The checks that compare questions need every pair in one call. This query has {questions, number, integer} questions, past the {most, number, integer} that fits, so they did not run.',
    'skipped.too_few_questions' => 'The checks that compare questions need two to compare. This run carried {questions, number, integer}, so they did not run.',
    'skipped.no_fields_to_name' => '`{id}` names a field at a time, and this state has none to name.',

    'report.no_usable_reading' => '`{key}` came back with no usable reading',
    'report.no_reading_from' => '`{id}` got no usable reading from {questions, plural, one {its question} other {any of its # questions}}',
    'report.partial_answer' => 'the call answered {answered, number, integer} of {asked, plural, one {# question} other {# questions}}; {missing} did not come back',

    'finding.pair_title' => '{title}: `{first}` and `{second}`',
    'finding.title_with_detail' => '{title}: {detail}',
    'finding.title_with_field' => '{title}: `{field}`',
    'finding.cleared_by' => 'the catalogue\'s clearing question read {probability, number, ::.00}, above its {trigger, number, ::.00} trigger',
    'finding.fired_by' => 'Raised by the catalogue\'s second question; the check\'s own question read {probability, number, ::.00} against its {trigger, number, ::.00} trigger.',

    'evidence.both_ask' => 'Both ask: "{first}" / "{second}"',
    'evidence.question_count' => '{count, plural, one {# question} other {# questions}}',
    'evidence.field_unread' => 'None of {asked} reads `{field}`.',
    'evidence.field_read' => 'Read by at least one of {asked}, so `{field}` stays.',
    'evidence.read' => 'Read: {what}',
    'evidence.read_quoted' => 'Read: "{what}"',
    'evidence.read_with' => 'Read: "{instructions}" with {criteria}',
    'evidence.field' => 'Field `{field}`.',
    'evidence.level_quoted' => ' ("{text}")',
    'evidence.level_of' => 'level {index, number, integer} of {levels, number, integer}{quoted}',
    'evidence.level' => 'level {index, number, integer}{quoted}',

    'readings.wordings_resettled' => '{wordings, plural, one {# wording} other {# wordings}}, asked again on the trigger',
    'readings.wordings_over_repeats' => '{wordings, plural, one {# wording} other {# wordings}} over {repeats, plural, one {# repeat} other {# repeats}}',
    'readings.wordings' => '{wordings, plural, one {# wording} other {# wordings}}',
    'readings.repeats' => '{repeats, plural, one {# repeat} other {# repeats}}',

    'type.agrees' => 'The answers this asks for fit the `{declared}` it is declared as.',
    'type.none_fits' => 'The answer this asks for is not a noul, a choice or a score, but it is declared a `{declared}`.',
    'type.looks_like' => 'The answer this asks for looks like a `{picked}`, but it is declared a `{declared}`.',
    'type.suppressed_catch_all' => 'the catalogue sets aside a `{picked}` answer on a Choice carrying a catch-all',
    'type.evidence' => '`{picked}` {picked_weight, number, ::.00} against the declared `{declared}` {declared_weight, number, ::.00}.',
    'report.header' => '{source} · catalogue v{version} {fingerprint} for {model}{pinned, select, yes {, asked through {through}} other {}}',
    'report.probability_note' => 'A probability is how strongly the defect is present, so higher is worse.',
    'report.nothing_ran' => 'No check ran. This query was not checked.',
    'report.all_hidden' => 'Nothing at or above this severity. {count, plural, one {# finding} other {# findings}} hidden by --min.',
    'report.only_undecided' => 'No findings, but a check could not decide. See below.',
    'report.nothing_to_report' => 'Nothing to report.',
    'report.cleared_all' => 'Ran and cleared',
    'report.cleared_near' => 'Cleared, and worth a look',
    'report.against_trigger' => '{probability, number, ::.00} against a {trigger, number, ::.00} trigger',
    'report.against_trigger_tail' => ' against a {trigger, number, ::.00} trigger',
    'report.probability' => '{probability, number, ::.00}',
    'report.close_to_the_line' => ', close to the line',
    'report.undecided_heading' => '{count, plural, one {# check} other {# checks}} could not decide: its readings fall on both sides of its trigger.',
    'report.undecided_row' => '{check} on {target} · {readings}',
    'report.check_on_target' => '{check} on {target}',
    'report.accepted_heading' => '{count, number, integer} accepted by {source}{listed, select, yes {:} other { · --show-accepted for the reasons}}',
    'report.calls_lost' => '{count, plural, one {# call} other {# calls}} could not be made, so those checks never ran. This run did not check your query.',
    'report.moot_if' => 'you act on `{check}` above, which changes the text this check read.',
    'report.also_drops' => '{checks} below, which read text this one tells you to replace.',
    'report.readings' => '{of}: {readings}, spread {spread}.',
    'report.patch' => '{safety} · {op} {path}',
    'report.patch_with_value' => '{safety} · {op} {path} = {value}',
    'report.patch_covered_by' => ' · {check} already removes this node, so apply one of them',
    'report.counts' => '{errors, plural, one {# error} other {# errors}}, {warnings, plural, one {# warning} other {# warnings}}, {advice, number, integer} advice',
    'report.no_calls' => ' · no calls made',
    'report.cost' => ' · {calls, plural, one {# call} other {# calls}}, {floor, select, yes {at least } other {}}{tokens} tokens',

    'readings.repeats_word' => 'repeats',
    'likelihood.certain' => 'certain, because this rule either matches or does not',
    'likelihood.weight' => '{weight} away from the primitive you declared, against a {trigger} trigger. This check asks which primitive fits, so the number is not a probability that anything is wrong',
    'likelihood.near_trigger' => ' it is within {near, number, ::.00} of, so it may not repeat',
    'likelihood.straddled' => ', and its own readings fall on both sides of that trigger',
    'likelihood.probability' => '{probability}, {band}, against a {trigger} trigger{near}{straddled}',
    'band.almost_certain' => 'almost certain',
    'band.very_likely' => 'very likely',
    'band.likely' => 'likely',
    'band.unlikely' => 'unlikely',
    'band.very_unlikely' => 'very unlikely',

    'severity.error' => 'error',
    'severity.warning' => 'warning',
    'severity.advice' => 'advice',

    'label.if_it_is' => 'If it is',
    'label.failed' => 'failed',
    'label.note' => 'note  ',
    'label.weight' => 'Weight',
    'label.likelihood' => 'Likelihood',
    'label.moot_if' => 'Moot if',
    'label.also_drops' => 'Also drops',
    'label.found' => 'Found',
    'label.readings' => 'Readings',
    'label.suggested' => 'Suggested',
    'label.advice' => 'Advice',
    'label.patch' => 'Patch',
    'label.why' => 'Why',
    'label.docs' => 'Docs',
    'label.caveat' => 'Caveat',
    'probe.header' => '{source} · {repeats, plural, one {# repeat} other {# repeats}} · {calls, plural, one {# call} other {# calls}}, {tokens} tokens',
    'probe.summary' => '{moved, number, integer} of {questions, plural, one {# question} other {# questions}} moved on a rewrite.',
    'probe.movers' => ' The {count, plural, one {rewrite} other {rewrites}} that moved: {names}.',
    'probe.criteria_stripped_moved' => ' `criteria-stripped` is the one rewrite that changes the question, so a move there is expected.',
    'probe.starred_legend' => 'A row is starred when it moved: the change cleared both three times the noise floor and {negligible, number, ::.00}. The floor is the spread measured over the repeats, or {floor, number, ::.0000} where that spread is smaller, which is the floor this tool uses. Repeats sent back to back understate real variability, so the floor is a floor.',
    'probe.unchanged_describe' => 'sent as written, several times, to measure the spread everything else is compared with',
    'probe.legend_heading' => 'What each rewrite changes:',
    'probe.no_reading' => 'no reading',
    'probe.noise' => '± {noise, number, ::.0000} over the repeats{below, select, yes {, below the published floor} other {}}',
    'probe.noise_ratio' => '{ratio, number, ::.} × the noise floor',
    'probe.undecided' => 'near enough to the middle that your threshold decides this question and not the query{flips, select, yes {, and the repeats fell on both sides of it} other {}}',
    'probe.undecided_summary' => ' {count, plural, one {# question} other {# questions}} answered near the middle as written.',
    'probe.undecided_definition' => 'A yes/no answer within {band, number, ::.00} of 0.5, where a threshold anywhere a caller would put it falls on either side. A Choice reports its winning label and a Score a position on its scale, so neither is counted.',

    'self_test.heading' => 'Each check asked about a question it should fire on, one it should not, and the broken one with its own suggestion applied.',
    'self_test.footer' => 'A check that does not separate them measures something other than what its title claims, whatever it reports about your query.',
    'self_test.summary' => '{separated, number, integer} of {sets, plural, one {# example set} other {# example sets}} separated, over {checks, plural, one {# check} other {# checks}}.',
    'self_test.column_check' => 'check',
    'self_test.column_clean' => 'clean',
    'self_test.column_broken' => 'broken',
    'self_test.column_fixed' => 'fixed',
    'self_test.column_span' => 'span',
    'self_test.column_verdict' => 'verdict',
    'help.usage' => 'jevlint <check|probe|self-test|checks> [options]',
    'help.command_check' => 'check a query against the catalogue',
    'help.command_probe' => 'measure what a rewrite does to the answers',
    'help.command_self_test' => 'check that the checks separate their own examples',
    'help.command_checks' => 'list the catalogue',
    'version.line' => 'jevlint {jevlint} · catalogue v{version} {fingerprint} for {model}',
    'version.covers' => 'Jev versions it holds checks for: {versions}. `latest` is {latest}.',
    'cli.no_such_command' => 'There is no "{command}" command. Try `jevlint help`.',
    'help.page' => <<<'ICU'
        jevlint - a linter for Jev queries

        USAGE
          jevlint check <query.json> [options]     check a query against the catalogue
          jevlint probe <query.json> [options]     measure what a rewrite does to the answers
          jevlint self-test [options]              check that the checks separate their own examples
          jevlint checks                           list the catalogue

        A query file is the request body you would send: a `state`, and `questions`
        keyed by id. `examples/` has one of each.

        CHECK OPTIONS
          --static-only        only the rules that need no call; costs nothing
          --no-state           skip the checks that need the state in front of them
          --min=<severity>     hide findings below error, warning or advice (default: advice);
                               it also moves the floor --strict fails on
          --brief              one line per finding, for a terminal you already know
          --repeats=<n>        ask the per-question checks n times and report the spread (default: 1)
          --question=<ids>     check only these questions, comma separated
          --only=<check ids>   run only these checks, comma separated
          --all                also report the model checks that ran and cleared
          --config=<file>      acceptances to apply (default: .jevlint.json beside the query)
          --jev=<version>      the Jev version the query runs against (default: latest)
          --show-accepted      print the findings the config accepts, with their reasons
          --strict             exit non-zero on any finding, not only on an error
          --max-state=<chars>  when to call the state large (default: 20000)
          --timeout=<seconds>  per API call (default: 10)
          --format=json        the report as JSON

        PROBE OPTIONS
          --state=<file>       state to run against, in place of any in the query file
          --repeats=<n>        how many times to send the query unchanged (default: 5)
          --variants=<file>    your own rewordings: '{'"name": '{'"question_id": "..."'}}'
          --question=<id,...>  probe only these questions
          --strict             exit non-zero when a rewrite moved an answer
          --format=json        the readings as JSON

        SELF-TEST OPTIONS
          --check=<id,...>     score only these checks (each costs about 6 calls)
          --jev=<version>      score the checks written for this version (default: latest)
          --config=<file>      read the pinned version from here (default: .jevlint.json)
          --format=json        the scores as JSON

          With no --check every model check is scored against both of its example
          sets, which is upwards of a hundred calls.

        CHECKS OPTIONS
          --jev=<version>      list the checks written for this version (default: latest)
          --config=<file>      read the pinned version from here (default: .jevlint.json)
          --format=json        the catalogue as JSON

          `jevlint checks <id>` prints one check in full. `--jev` takes a version
          the catalogue covers, or `latest`; `jevlint --version` lists them. A
          repository pins one for check, checks and self-test by putting "jev" in
          .jevlint.json. `probe` reads no checks, so it takes neither option.

        EVERYWHERE
          --model=<name>       a pinned build, as the API names it, such as jev-1.13.0 (default: the SDK's)
          --openrouter         call through OpenRouter and read OPENROUTER_API_KEY
          --env-file=<file>    read the key from here, not from ./.env
          --lang=<locale>      answer in this language, such as fr or pt_BR
                               (default: JEVLINT_LANG, then LC_ALL, LC_MESSAGES or LANG)
          --no-color           plain output
          --version            the tool and the catalogue it would load

        EXIT CODES
          0  nothing at error severity, and nothing left undecided. Warnings and
             advice exit 0 on their own, which is what --strict is for
          1  an error, --strict with any finding at or above --min, a rewrite that
             moved an answer under --strict, or a check that failed its own examples
          2  could not run: a call that failed, a file that would not load, a bad
             option, or a run that was narrowed until no check was left to ask
          3  no errors, but a check could not decide: its readings fell on both
             sides of its trigger, so the verdict would not repeat

        ICU,
    'words.fallback_labels' => ['other', 'others', 'none', 'none_of_the_above', 'none of the above', 'unknown', 'unclear', 'not_stated', 'not stated', 'n/a', 'neither', 'something_else', 'something else', 'no date given', 'not applicable', 'no answer'],
    'words.catch_all_phrases' => [
        'the other options do not cover',
        'the others do not cover',
        'the other two do not cover',
        'none of the above',
        'anything else',
        'everything else',
        'does not fit',
        'do not fit',
        'not covered',
        'any other',
        // The other shape a catch-all takes: the option that collects the cases
        // where the material answers none of the rest because it says nothing.
        'does not state',
        'do not state',
        'is not stated',
        'not given',
        'no date is given',
        'nothing is recorded',
        'not recorded',
        'cannot be determined',
    ],
    'words.grammar' => ['is', 'are', 'was', 'were', 'be', 'been', 'does', 'do', 'did', 'has', 'have', 'had', 'the', 'a', 'an', 'this', 'that', 'these', 'those', 'it', 'its', 'of', 'to', 'in', 'on', 'at', 'for', 'and', 'or', 'any', 'there', 'which', 'what', 'who', 'whom', 'whose', 'when', 'where', 'how', 'why'],
    'patch.lossless' => 'nothing you wrote is lost',
    'patch.lossy' => 'what you wrote survives, something around it changes',
    'patch.destructive' => 'it takes a question or a field out of the query',
    'patch.legend' => 'A patch says what kind of change it is: {kinds}.',
    'patch.fallback_option' => 'Anything the other options do not cover',
    'evidence.keys_are_numbers' => 'The keys are numbers, so the levels are ordered by them.',
    'evidence.keys_are_names' => 'The keys are names, so nothing says which order the levels run in.',
    'report.resettle_failed' => 'the borderline checks could not be asked again - {detail}',
    'readings.one_and_a_resettle' => 'one reading and a re-ask on the trigger',
    'probe.needs_state' => 'A probe needs state to run the query against. Put it in the file or pass --state.',
    'probe.nothing_sendable' => 'None of the questions in this query can be sent.',
    'probe.reading_yes' => 'probability of yes',
    'probe.call_failed' => 'the call failed',
    'narrow.no_question_named' => '--question was given nothing to narrow to. Name a question, or leave the option off.',
    'narrow.no_check_named' => '--check was given nothing to score. Name a check, or leave the option off.',
];
